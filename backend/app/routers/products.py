from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, User, UserRole
from ..schemas import ProductUpdate
from ..security import get_current_user, require_roles
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


@router.get("/{product_id}")
def get_product(
    product_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product_to_dict(product)


@router.patch("/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product_to_dict(product)
