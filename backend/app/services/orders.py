from __future__ import annotations

from ..models import (
    ORDER_TRANSITIONS,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    User,
    utc_now,
)
from .movements import apply_movement


def order_to_dict(order: PurchaseOrder) -> dict:
    return {
        "id": order.id,
        "supplier_id": order.supplier_id,
        "supplier_name": order.supplier_name,
        "status": order.status,
        "note": order.note,
        "total_amount": order.total_amount,
        "created_by_name": order.created_by_name,
        "created_at": order.created_at,
        "sent_at": order.sent_at,
        "received_at": order.received_at,
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "sku": i.sku,
                "name": i.name,
                "quantity": i.quantity,
                "purchase_price": i.purchase_price,
                "line_total": i.line_total,
            }
            for i in order.items
        ],
        "item_count": len(order.items),
    }


def create_orders_from_plan(db, user: User, items: list[dict], note: str = "") -> list[PurchaseOrder]:
    """Build draft purchase orders from plan lines, grouped by supplier.

    Each line is {product_id, quantity}. Lines for the same supplier land in one
    order; lines without a supplier go into a single "no supplier" order.
    Raises ValueError if no valid products are found.
    """
    # Resolve products and group by supplier.
    groups: dict[int | None, list[tuple[Product, int]]] = {}
    for line in items:
        product = db.query(Product).filter(Product.id == line["product_id"]).first()
        if not product:
            continue
        groups.setdefault(product.supplier_id, []).append((product, line["quantity"]))

    if not groups:
        raise ValueError("Не найдено товаров для заказа")

    suppliers = {s.id: s for s in db.query(Supplier).all()}
    created: list[PurchaseOrder] = []
    for supplier_id, rows in groups.items():
        supplier = suppliers.get(supplier_id) if supplier_id else None
        order = PurchaseOrder(
            supplier_id=supplier_id,
            supplier_name=supplier.name if supplier else "",
            status="draft",
            note=note,
            created_by_id=user.id if user else None,
            created_by_name=(user.full_name or user.username) if user else "",
        )
        total = 0.0
        for product, qty in rows:
            line_total = round(qty * product.purchase_price, 2)
            total += line_total
            order.items.append(
                PurchaseOrderItem(
                    product_id=product.id,
                    sku=product.sku,
                    name=product.name,
                    quantity=qty,
                    purchase_price=product.purchase_price,
                    line_total=line_total,
                )
            )
        order.total_amount = round(total, 2)
        db.add(order)
        created.append(order)

    return created


def transition_order(db, user: User, order: PurchaseOrder, new_status: str) -> None:
    """Move an order to a new status, enforcing the allowed transitions.

    Moving to "received" applies a receipt movement for every line so stock and
    the movement journal stay in sync. Raises ValueError on an illegal move.
    """
    allowed = ORDER_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise ValueError(f"Недопустимый переход статуса: {order.status} → {new_status}")

    if new_status == "sent":
        order.sent_at = utc_now()
    elif new_status == "received":
        order.received_at = utc_now()
        _apply_received(db, user, order)

    order.status = new_status


def _apply_received(db, user: User, order: PurchaseOrder) -> None:
    for item in order.items:
        if not item.product_id or item.quantity <= 0:
            continue
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            apply_movement(
                db, product, user, "receipt", item.quantity,
                note=f"Приход по заказу #{order.id}",
            )
