from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AiStatusResponse, ChatRequest, ChatResponse
from ..security import get_current_user
from ..services.ai_service import ai_status, chat_with_ai


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = [turn.model_dump() for turn in body.history]
    return chat_with_ai(db, body.message, history)


@router.get("/status", response_model=AiStatusResponse)
def status(_: User = Depends(get_current_user)):
    return ai_status()
