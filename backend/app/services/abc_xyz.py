from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from ..models import Product, ProductSnapshot


# ABC by cumulative revenue share; XYZ by demand variability (coefficient of
# variation across import snapshots).
ABC_THRESHOLDS = (0.80, 0.95)  # A up to 80%, B up to 95%, C the rest
XYZ_THRESHOLDS = (0.10, 0.25)  # X cv<=10%, Y cv<=25%, Z above

RECOMMENDATIONS = {
    "AX": "Ключевой стабильный товар — держать запас, не допускать дефицита.",
    "AY": "Важный товар с колебаниями спроса — страховой запас выше среднего.",
    "AZ": "Важный, но нестабильный — закупать аккуратно, следить вручную.",
    "BX": "Стабильный середняк — закупка по плану.",
    "BY": "Середняк с колебаниями — умеренный страховой запас.",
    "BZ": "Нестабильный середняк — закупать малыми партиями.",
    "CX": "Дешёвый стабильный — можно минимизировать запас.",
    "CY": "Малозначимый с колебаниями — закупка под спрос.",
    "CZ": "Кандидат на вывод из ассортимента или распродажу.",
}


def _xyz_class(cv: float | None) -> str | None:
    if cv is None:
        return None
    x, y = XYZ_THRESHOLDS
    if cv <= x:
        return "X"
    if cv <= y:
        return "Y"
    return "Z"


def _demand_cv(values: list[float]) -> float | None:
    """Coefficient of variation; needs >=2 points and a non-zero mean."""
    if len(values) < 2:
        return None
    avg = mean(values)
    if avg == 0:
        return None
    return pstdev(values) / avg


def compute_abc_xyz(db: Session) -> dict:
    products = db.query(Product).all()
    if not products:
        return {"rows": [], "matrix": {}, "totals": {"revenue": 0, "products": 0}}

    # ── ABC: rank by monthly revenue, accumulate share ───────────────────────
    revenues = {p.id: p.sold_month * p.sale_price for p in products}
    total_revenue = sum(revenues.values())
    ranked = sorted(products, key=lambda p: revenues[p.id], reverse=True)

    a_thr, b_thr = ABC_THRESHOLDS
    abc: dict[int, str] = {}
    cumulative = 0.0
    for p in ranked:
        # Classify by the cumulative share BEFORE this item, so the boundary
        # item that crosses a threshold belongs to the more important class
        # (e.g. a single item worth >95% of revenue is still A, not C).
        if total_revenue == 0:
            abc[p.id] = "C"
        elif cumulative < a_thr:
            abc[p.id] = "A"
        elif cumulative < b_thr:
            abc[p.id] = "B"
        else:
            abc[p.id] = "C"
        cumulative += (revenues[p.id] / total_revenue) if total_revenue else 0

    # ── XYZ: variability of sold_month across snapshots, by SKU ───────────────
    history: dict[str, list[tuple]] = defaultdict(list)
    snapshots = (
        db.query(ProductSnapshot)
        .order_by(ProductSnapshot.created_at.asc())
        .all()
    )
    for s in snapshots:
        history[s.sku].append(s.sold_month)

    rows = []
    matrix: dict[str, int] = defaultdict(int)
    for p in products:
        cv = _demand_cv([float(v) for v in history.get(p.sku, [])])
        xyz = _xyz_class(cv)
        combo = f"{abc[p.id]}{xyz}" if xyz else None
        if combo:
            matrix[combo] += 1
        rows.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "revenue": round(revenues[p.id], 2),
                "revenue_share": round((revenues[p.id] / total_revenue) * 100, 1) if total_revenue else 0,
                "abc": abc[p.id],
                "xyz": xyz,
                "cv": round(cv, 2) if cv is not None else None,
                "combo": combo,
                "recommendation": RECOMMENDATIONS.get(combo, "Недостаточно истории продаж для XYZ.") if combo else "Недостаточно истории продаж для XYZ.",
            }
        )

    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return {
        "rows": rows,
        "matrix": dict(matrix),
        "totals": {"revenue": round(total_revenue, 2), "products": len(products)},
    }
