from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Notification, Product
from .analytics import product_signal


# State alerts are recomputed from the current warehouse state on every scan.
# Event alerts (e.g. import warnings) are records of something that happened and
# are kept until the user reads them.
STATE_TYPES = ("low_stock", "dead_stock", "margin_low")

MARGIN_FLOOR_PERCENT = 15.0


def scan_notifications(db: Session) -> dict:
    """Rebuild state-based alerts from current products. Returns counts."""
    db.query(Notification).filter(Notification.type.in_(STATE_TYPES)).delete(synchronize_session=False)

    created = 0
    products = db.query(Product).order_by(Product.name.asc()).all()
    for p in products:
        signal = product_signal(p)
        code = signal["status_code"]

        if code in {"out_of_stock", "order_now"} and not p.do_not_order:
            days = signal.get("days_left")
            tail = f"остатка хватит на ~{days} дн." if days is not None else "позиция закончилась"
            db.add(
                Notification(
                    type="low_stock",
                    severity="critical" if code == "out_of_stock" else "warning",
                    title=f"Скоро закончится: {p.name}",
                    message=f"{p.sku}: остаток {p.stock} шт., {tail}. Срок поставки {p.lead_time_days} дн.",
                    product_id=p.id,
                )
            )
            created += 1
        elif code in {"dead_stock", "discount"}:
            dwos = signal.get("days_without_sales")
            tail = f"нет продаж {dwos} дн." if dwos is not None else "продажи остановились"
            db.add(
                Notification(
                    type="dead_stock",
                    severity="warning" if code == "dead_stock" else "notice",
                    title=f"Залежавшийся товар: {p.name}",
                    message=f"{p.sku}: {tail}, остаток {p.stock} шт. Рассмотрите скидку или распродажу.",
                    product_id=p.id,
                )
            )
            created += 1

        if p.sale_price > 0 and signal["margin_percent"] < MARGIN_FLOOR_PERCENT:
            db.add(
                Notification(
                    type="margin_low",
                    severity="notice",
                    title=f"Низкая маржа: {p.name}",
                    message=f"{p.sku}: маржа {signal['margin_percent']}% (порог {MARGIN_FLOOR_PERCENT:.0f}%). Проверьте цену.",
                    product_id=p.id,
                )
            )
            created += 1

    db.commit()
    return {"created": created}


def add_import_notification(db: Session, batch, warnings: list[str]) -> None:
    """Record an event notification for a finished import (with warnings)."""
    if warnings:
        severity = "warning"
        message = f"Импорт «{batch.filename}»: {batch.rows_count} строк, {len(warnings)} предупреждений."
    else:
        severity = "notice"
        message = f"Импорт «{batch.filename}»: {batch.rows_count} строк, без ошибок."
    db.add(
        Notification(
            type="import_warning",
            severity=severity,
            title="Импорт завершён",
            message=message,
        )
    )
    db.commit()


def unread_count(db: Session) -> int:
    return db.query(Notification).filter(Notification.is_read == False).count()  # noqa: E712
