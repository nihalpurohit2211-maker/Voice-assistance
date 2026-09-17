from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid

from backend.db.session import get_db
from backend.db.models import ChatSession, ChatMessage, User
from backend.routers.auth import get_current_user

router = APIRouter()

@router.get("/chats")
async def get_chats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(ChatSession).where(ChatSession.user_id == current_user.id).order_by(ChatSession.started_at.desc())
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [
        {
            "id": str(s.id),
            "started_at": s.started_at.isoformat(),
            "ended_at": s.ended_at.isoformat() if s.ended_at else None
        }
        for s in sessions
    ]

@router.get("/chats/{session_id}")
async def get_chat_details(session_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalars().first()
    
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
        
    msg_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()
    
    return {
        "id": str(session.id),
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "was_interrupted": m.was_interrupted,
                "intent": m.intent,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    }
