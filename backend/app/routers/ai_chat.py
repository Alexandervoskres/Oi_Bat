from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ChatRequest, ChatResponse
from ..security import get_current_user
from ..services.ai_service import chat_with_ai


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_with_ai(db, body.message)
