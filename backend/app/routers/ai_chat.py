from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AiStatusResponse, ChatRequest, ChatResponse
from ..security import get_current_user
from ..services.ai_service import ai_status, chat_stream, chat_with_ai


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = [turn.model_dump() for turn in body.history]
    return chat_with_ai(db, body.message, history)


@router.post("/chat/stream")
def chat_stream_endpoint(
    body: ChatRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = [turn.model_dump() for turn in body.history]

    def event_source():
        try:
            for event in chat_stream(db, body.message, history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # never break the stream contract
            err = {
                "type": "done",
                "replace": True,
                "agent": "StoreAI",
                "source": "error",
                "answer": f"Не удалось получить ответ: {exc}",
                "suggested_actions": [],
                "used_products": [],
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status", response_model=AiStatusResponse)
def status(_: User = Depends(get_current_user)):
    return ai_status()
