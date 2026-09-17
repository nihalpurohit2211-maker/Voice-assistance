from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid

from backend.db.session import get_db
from backend.db.models import Memory, User
from backend.routers.auth import get_current_user

router = APIRouter()

@router.get("/memories")
async def get_memories(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Memory).where(Memory.user_id == current_user.id).order_by(Memory.created_at.desc()))
    memories = result.scalars().all()
    return [{"id": str(m.id), "text": m.text_content, "created_at": m.created_at.isoformat()} for m in memories]

@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalars().first()
    
    if not memory or memory.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
        
    await db.delete(memory)
    await db.commit()
    return {"status": "success"}
