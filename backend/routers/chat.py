from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import uuid
from sqlalchemy.future import select

from backend.services.pipeline import run_pipeline
from backend.db.session import async_session_maker
from backend.db.models import User, ChatSession, ChatMessage
from backend.routers.auth import get_current_user

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[uuid.UUID] = None
    mode: Optional[str] = None

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        session_id = request.session_id
        async with async_session_maker() as db:
            sess = None
            if session_id:
                result = await db.execute(
                    select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
                )
                sess = result.scalars().first()
            
            if not sess:
                sess = ChatSession(user_id=current_user.id)
                db.add(sess)
                await db.commit()
                await db.refresh(sess)
            
            session_id = sess.id

        result = await run_pipeline(
            current_user.id, 
            request.message, 
            session_id=session_id, 
            mode_override=request.mode
        )

        async with async_session_maker() as db:
            user_msg = ChatMessage(session_id=session_id, role="user", content=request.message, intent=result.get("intent"))
            asst_msg = ChatMessage(session_id=session_id, role="assistant", content=result.get("reply"), was_interrupted=False)
            db.add(user_msg)
            db.add(asst_msg)
            await db.commit()

        return {
            "reply": result.get("reply"),
            "intent": result.get("intent"),
            "mode": result.get("mode"),
            "session_id": str(session_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

