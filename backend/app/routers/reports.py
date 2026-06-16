from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..security import require_roles
from ..services.audit import record_audit
from ..services.pdf_report import build_risk_pdf


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/risk.pdf")
def risk_pdf(
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.buyer)),
    db: Session = Depends(get_db),
):
    payload = BytesIO(build_risk_pdf(db))
    record_audit(db, user, "report.download", entity_type="report", detail="Скачан PDF-отчёт по рискам")
    return StreamingResponse(
        payload,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="skladai-risk-report.pdf"'},
    )
