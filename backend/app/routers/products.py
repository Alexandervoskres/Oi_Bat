from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, StockMovement, User, UserRole, utc_now
from ..schemas import MovementCreate, MovementOut, ProductCreate, ProductRiskUpdate, ProductUpdate
from ..security import get_current_user, require_roles
from ..services.analytics import product_to_dict
from ..services.audit import record_audit
from ..services.movements import MOVEMENT_LABELS, apply_movement


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
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    existing = db.query(Product).filter(Product.sku == body.sku).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Товар с артикулом '{body.sku}' уже существует")

    product = Product(**body.model_dump())
    db.add(product)
    db.flush()
    record_audit(
        db, user, "product.create", entity_type="product", entity_id=product.id,
        detail=f"Создан товар {product.sku} «{product.name}»", commit=False,
    )
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

    changed = ", ".join(sorted(updates.keys()))
    record_audit(
        db, user, "product.update", entity_type="product", entity_id=product.id,
        detail=f"Изменён товар {product.sku}: поля {changed}", commit=False,
    )
    db.commit()
    db.refresh(product)
    return product_to_dict(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    user: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    record_audit(
        db, user, "product.delete", entity_type="product", entity_id=product.id,
        detail=f"Удалён товар {product.sku} «{product.name}»", commit=False,
    )
    db.delete(product)
    db.commit()
    return Response(status_code=204)


@router.patch("/{product_id}/risk")
def update_risk(
    product_id: int,
    body: ProductRiskUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
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
    record_audit(
        db, user, "product.risk", entity_type="product", entity_id=product.id,
        detail=f"Корректировка риска {product.sku}: {', '.join(sorted(data.keys())) or 'без изменений'}",
        commit=False,
    )
    db.commit()
    db.refresh(product)
    return product_to_dict(product)


@router.get("/{product_id}/movements", response_model=list[MovementOut])
def list_movements(
    product_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return (
        db.query(StockMovement)
        .filter(StockMovement.product_id == product_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(200)
        .all()
    )


@router.post("/{product_id}/movements", response_model=MovementOut, status_code=201)
def create_movement(
    product_id: int,
    body: MovementCreate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    try:
        movement = apply_movement(db, product, user, body.movement_type, body.quantity, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.flush()
    label = MOVEMENT_LABELS.get(body.movement_type, body.movement_type)
    record_audit(
        db, user, "stock.movement", entity_type="product", entity_id=product.id,
        detail=f"{label} {movement.quantity:+d} → остаток {movement.stock_after} ({product.sku})",
        commit=False,
    )
    db.commit()
    db.refresh(movement)
    return movement
