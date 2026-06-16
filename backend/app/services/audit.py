from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog, User


def record_audit(
    db: Session,
    user: User | None,
    action: str,
    *,
    entity_type: str = "",
    entity_id: int | None = None,
    detail: str = "",
    commit: bool = True,
) -> AuditLog:
    """Append an audit entry.

    The username is denormalized so the trail survives user deletion. By default
    this commits, but callers already inside a transaction can pass commit=False
    and commit the surrounding unit of work themselves.
    """
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail[:2000],
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
