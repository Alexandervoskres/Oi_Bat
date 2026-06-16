from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, Supplier, User, UserRole
from ..schemas import SupplierCreate, SupplierOut, SupplierUpdate
from ..security import get_current_user, require_roles
from ..services.audit import record_audit


router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _serialize(supplier: Supplier, product_count: int) -> dict:
    return {
        "id": supplier.id,
        "name": supplier.name,
        "contact_person": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
        "reliability": supplier.reliability,
        "min_order_amount": supplier.min_order_amount,
        "payment_terms": supplier.payment_terms,
        "lead_time_days": supplier.lead_time_days,
        "notes": supplier.notes,
        "product_count": product_count,
        "created_at": supplier.created_at,
    }


@router.get("", response_model=list[SupplierOut])
def list_suppliers(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    counts = dict(
        db.query(Product.supplier_id, func.count(Product.id))
        .filter(Product.supplier_id.isnot(None))
        .group_by(Product.supplier_id)
        .all()
    )
    suppliers = db.query(Supplier).order_by(Supplier.name.asc()).all()
    return [_serialize(s, counts.get(s.id, 0)) for s in suppliers]


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(
    body: SupplierCreate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    if db.query(Supplier).filter(Supplier.name == body.name).first():
        raise HTTPException(status_code=409, detail=f"Поставщик «{body.name}» уже существует")

    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    db.flush()
    record_audit(
        db, user, "supplier.create", entity_type="supplier", entity_id=supplier.id,
        detail=f"Создан поставщик «{supplier.name}»", commit=False,
    )
    db.commit()
    db.refresh(supplier)
    return _serialize(supplier, 0)


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    body: SupplierUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Поставщик не найден")

    updates = body.model_dump(exclude_none=True)
    if "name" in updates and updates["name"] != supplier.name:
        clash = db.query(Supplier).filter(Supplier.name == updates["name"], Supplier.id != supplier_id).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Поставщик «{updates['name']}» уже существует")

    for field, value in updates.items():
        setattr(supplier, field, value)

    record_audit(
        db, user, "supplier.update", entity_type="supplier", entity_id=supplier.id,
        detail=f"Изменён поставщик «{supplier.name}»: {', '.join(sorted(updates.keys()))}", commit=False,
    )
    db.commit()
    db.refresh(supplier)
    count = db.query(func.count(Product.id)).filter(Product.supplier_id == supplier.id).scalar() or 0
    return _serialize(supplier, count)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    user: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Поставщик не найден")

    # Detach products from the supplier rather than blocking deletion.
    db.query(Product).filter(Product.supplier_id == supplier_id).update(
        {Product.supplier_id: None}, synchronize_session=False
    )
    record_audit(
        db, user, "supplier.delete", entity_type="supplier", entity_id=supplier.id,
        detail=f"Удалён поставщик «{supplier.name}»", commit=False,
    )
    db.delete(supplier)
    db.commit()
    return Response(status_code=204)
