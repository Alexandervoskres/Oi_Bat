from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User, UserRole
from ..schemas import AuditOut
from ..security import require_roles


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(
    action: str = Query(default=""),
    entity_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
