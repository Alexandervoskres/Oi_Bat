from __future__ import annotations

import math

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, User
from ..security import get_current_user
from ..services.analytics import product_signal


router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("")
def get_procurement_plan(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    products = (
        db.query(Product)
        .filter(Product.do_not_order == False)  # noqa: E712
        .order_by(Product.name.asc())
        .all()
    )

    rows = []
    for p in products:
        signal = product_signal(p)
        if signal["severity"] not in {"critical", "warning"}:
            continue

        demand = max(float(p.avg_monthly_sales or 0), float(p.sold_month or 0))
        # Target: enough stock to survive lead time + 1 month buffer + min_stock cushion
        target = math.ceil(demand * (p.lead_time_days / 30 + 1)) + p.min_stock
        recommended_qty = max(0, target - p.stock)
        if recommended_qty == 0:
            continue

        rows.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "stock": p.stock,
                "min_stock": p.min_stock,
                "avg_monthly_sales": p.avg_monthly_sales,
                "lead_time_days": p.lead_time_days,
                "supplier": p.supplier,
                "purchase_price": p.purchase_price,
                "recommended_qty": recommended_qty,
                "total_cost": round(recommended_qty * p.purchase_price, 2),
                "status": signal["status"],
                "severity": signal["severity"],
                "days_left": signal["days_left"],
                "is_seasonal": p.is_seasonal,
                "is_on_demand": p.is_on_demand,
            }
        )

    rows.sort(
        key=lambda r: (
            0 if r["severity"] == "critical" else 1,
            r["days_left"] if r["days_left"] is not None else 9999,
        )
    )
    return rows
