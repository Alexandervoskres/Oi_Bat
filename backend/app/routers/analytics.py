from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import DashboardResponse
from ..security import get_current_user
from ..services.ai_service import build_ai_summary
from ..services.analytics import build_dashboard


router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ai_summary = build_ai_summary(db)
    return build_dashboard(db, ai_summary)


@router.get("/health")
def health():
    return {"status": "ok", "service": "СкладAI"}
