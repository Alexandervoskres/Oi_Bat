from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, User
from ..security import get_current_user
from ..services.analytics import product_to_dict


router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
def list_products(
    search: str = Query(default=""),
    status: str = Query(default=""),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if search:
        like = f"%{search}%"
        query = query.filter((Product.name.ilike(like)) | (Product.sku.ilike(like)) | (Product.category.ilike(like)))

    rows = [product_to_dict(product) for product in query.order_by(Product.category.asc(), Product.name.asc()).all()]
    if status:
        rows = [row for row in rows if row["status"] == status]
    return rows
