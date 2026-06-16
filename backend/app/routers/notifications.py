from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User, UserRole
from ..schemas import NotificationList
from ..security import get_current_user, require_roles
from ..services.notifications import scan_notifications, unread_count


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
def list_notifications(
    only_unread: bool = Query(default=False),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification)
    if only_unread:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    items = query.order_by(Notification.is_read.asc(), Notification.created_at.desc()).limit(200).all()
    return {"items": items, "unread": unread_count(db)}


@router.post("/scan", response_model=NotificationList)
def scan(
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    scan_notifications(db)
    items = (
        db.query(Notification)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .limit(200)
        .all()
    )
    return {"items": items, "unread": unread_count(db)}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(
    notification_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(Notification).filter(Notification.id == notification_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    note.is_read = True
    db.commit()
    return Response(status_code=204)


@router.post("/read-all", status_code=204)
def mark_all_read(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(Notification.is_read == False).update(  # noqa: E712
        {Notification.is_read: True}, synchronize_session=False
    )
    db.commit()
    return Response(status_code=204)
