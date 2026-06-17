from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PurchaseOrder, User, UserRole
from ..schemas import OrderCreateFromPlan, OrderOut, OrderStatusUpdate
from ..security import get_current_user, require_roles
from ..services.audit import record_audit
from ..services.orders import create_orders_from_plan, order_to_dict, transition_order


router = APIRouter(prefix="/api/orders", tags=["orders"])

STATUS_LABELS = {"draft": "черновик", "sent": "отправлен", "received": "получен", "cancelled": "отменён"}


@router.get("", response_model=list[OrderOut])
def list_orders(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    orders = db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()).all()
    return [order_to_dict(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order_to_dict(order)


@router.post("/from-plan", response_model=list[OrderOut], status_code=201)
def create_from_plan(
    body: OrderCreateFromPlan,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    try:
        orders = create_orders_from_plan(db, user, [i.model_dump() for i in body.items], body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.flush()
    for order in orders:
        record_audit(
            db, user, "order.create", entity_type="order", entity_id=order.id,
            detail=f"Создан заказ #{order.id} ({order.supplier_name or 'без поставщика'}, {len(order.items)} поз., {order.total_amount:.0f} ₽)",
            commit=False,
        )
    db.commit()
    for order in orders:
        db.refresh(order)
    return [order_to_dict(o) for o in orders]


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_status(
    order_id: int,
    body: OrderStatusUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    try:
        transition_order(db, user, order, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit(
        db, user, "order.status", entity_type="order", entity_id=order.id,
        detail=f"Заказ #{order.id}: статус → {STATUS_LABELS.get(order.status, order.status)}",
        commit=False,
    )
    db.commit()
    db.refresh(order)
    return order_to_dict(order)


@router.delete("/{order_id}", status_code=204)
def delete_order(
    order_id: int,
    user: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    record_audit(
        db, user, "order.delete", entity_type="order", entity_id=order.id,
        detail=f"Удалён заказ #{order.id}", commit=False,
    )
    db.delete(order)
    db.commit()
    return Response(status_code=204)
