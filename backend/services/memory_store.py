from sqlalchemy.future import select
from backend.db.models import Memory
from backend.services.embeddings import embed
from backend.db.session import async_session_maker
import uuid

async def save_memory(user_id: uuid.UUID, text: str) -> Memory:
    embedding = embed(text)
    async with async_session_maker() as db:
        new_memory = Memory(user_id=user_id, text_content=text, embedding=embedding)
        db.add(new_memory)
        await db.commit()
        await db.refresh(new_memory)
        return new_memory

async def retrieve_memories(user_id: uuid.UUID, query_text: str, limit: int = 5) -> list[str]:
    query_embedding = embed(query_text)
    async with async_session_maker() as db:
        stmt = (
            select(Memory.text_content)
            .where(Memory.user_id == user_id)
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
