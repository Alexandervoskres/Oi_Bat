from __future__ import annotations

from ..models import MOVEMENT_SIGN, MovementType, Product, StockMovement, User


MOVEMENT_LABELS = {
    "receipt": "Приход",
    "write_off": "Списание",
    "sale": "Продажа",
    "adjustment": "Корректировка",
    "return": "Возврат",
    "reserve": "Резерв",
}


def signed_delta(movement_type: str, quantity: int) -> int:
    """Resolve the signed stock change for a movement.

    For typed moves the request quantity is treated as a positive magnitude.
    `adjustment` keeps its own sign so a count correction can be negative.
    """
    mtype = MovementType(movement_type)
    if mtype is MovementType.adjustment:
        return quantity
    return abs(quantity) * MOVEMENT_SIGN[mtype]


def apply_movement(
    db,
    product: Product,
    user: User | None,
    movement_type: str,
    quantity: int,
    note: str = "",
) -> StockMovement:
    """Apply a stock movement to a product and record it.

    Raises ValueError on an invalid quantity or one that would drive stock
    negative. Does not commit — the caller owns the transaction.
    """
    if quantity == 0:
        raise ValueError("Количество движения не может быть нулевым")

    delta = signed_delta(movement_type, quantity)
    stock_before = product.stock
    stock_after = stock_before + delta
    if stock_after < 0:
        raise ValueError(
            f"Недостаточно остатка: на складе {stock_before} шт., "
            f"движение уводит остаток в минус ({stock_after})"
        )

    product.stock = stock_after
    movement = StockMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity=delta,
        stock_before=stock_before,
        stock_after=stock_after,
        note=note,
        created_by_id=user.id if user else None,
        created_by_name=(user.full_name or user.username) if user else "",
    )
    db.add(movement)
    return movement
