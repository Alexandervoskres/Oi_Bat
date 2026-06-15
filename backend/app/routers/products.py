from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, User, UserRole, utc_now
from ..schemas import ProductCreate, ProductRiskUpdate, ProductUpdate
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


@router.post("", status_code=201)
def create_product(
    body: ProductCreate,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    existing = db.query(Product).filter(Product.sku == body.sku).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Товар с артикулом '{body.sku}' уже существует")

    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product_to_dict(product)


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

    updates = body.model_dump(exclude_none=True)
    if "sku" in updates and updates["sku"] != product.sku:
        clash = db.query(Product).filter(Product.sku == updates["sku"], Product.id != product.id).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Артикул '{updates['sku']}' уже занят")

    for field, value in updates.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product_to_dict(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    _: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    db.delete(product)
    db.commit()
    return Response(status_code=204)


@router.patch("/{product_id}/risk")
def update_risk(
    product_id: int,
    body: ProductRiskUpdate,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    data = body.model_dump(exclude_unset=True)
    if "risk_status_override" in data:
        value = data["risk_status_override"]
        product.risk_status_override = value or None  # "" clears the override
    for field in ("risk_priority", "risk_note", "excluded_from_ai", "do_not_order", "is_seasonal", "risk_resolved_at"):
        if field in data:
            setattr(product, field, data[field])

    product.risk_updated_at = utc_now()
    db.commit()
    db.refresh(product)
    return product_to_dict(product)
