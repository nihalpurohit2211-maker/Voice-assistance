import uuid
import math
import logging
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.sql import func
from backend.db.models import Memory
from backend.services.embeddings import embed
from backend.services.llm_client import complete
from backend.db.session import async_session_maker

logger = logging.getLogger(__name__)

CONTRADICTION_PROMPT = """Does the new statement contradict, correct, or directly update the old statement?
Answer with exactly YES or NO.

Old: "{old_text}"
New: "{new_text}"
"""

async def save_memory(user_id: uuid.UUID, text: str) -> Memory:
    embedding = embed(text)
    
    async with async_session_maker() as db:
        # Check similarity against user's existing active (non-superseded) memories
        distance_col = Memory.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(Memory, distance_col)
            .where(Memory.user_id == user_id, Memory.superseded == False)
            .order_by("distance")
            .limit(5)
        )
        result = await db.execute(stmt)
        candidates = result.all()
        
        # 1. Near-duplicate check (similarity > 0.90 => distance < 0.10)
        for mem, dist in candidates:
            similarity = 1.0 - dist
            if similarity >= 0.90:
                logger.info(f"Near duplicate detected ({similarity:.3f}). Updating timestamp of memory {mem.id}")
                mem.created_at = func.now()
                await db.commit()
                await db.refresh(mem)
                return mem
                
        # 2. Contradiction / update check (similarity >= 0.65 => distance <= 0.35)
        for mem, dist in candidates:
            similarity = 1.0 - dist
            if similarity >= 0.65:
                try:
                    eval_res = await complete(
                        CONTRADICTION_PROMPT.format(old_text=mem.text_content, new_text=text),
                        [{"role": "user", "content": "Analyze whether the new statement contradicts or updates the old one."}]
                    )
                    eval_res = eval_res.strip().upper()
                    if eval_res.startswith("YES"):
                        logger.info(f"Contradiction detected with memory {mem.id}. Marking as superseded.")
                        mem.superseded = True
                except Exception as e:
                    logger.error(f"Error checking contradiction with LLM: {e}")
                    
        # Insert new memory
        new_memory = Memory(user_id=user_id, text_content=text, embedding=embedding, superseded=False)
        db.add(new_memory)
        await db.commit()
        await db.refresh(new_memory)
        return new_memory

async def retrieve_memories(user_id: uuid.UUID, query_text: str, limit: int = 5, distance_threshold: float = 0.50, half_life_days: float = 14.0) -> list[str]:
    query_embedding = embed(query_text)
    now = datetime.now(timezone.utc)
    
    async with async_session_maker() as db:
        distance_col = Memory.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Memory, distance_col)
            .where(
                Memory.user_id == user_id,
                Memory.superseded == False,
                distance_col < distance_threshold
            )
            .order_by("distance")
            .limit(20)  # Fetch candidate pool for recency re-ranking
        )
        result = await db.execute(stmt)
        candidates = result.all()
        
        if not candidates:
            return []
            
        scored = []
        for mem, dist in candidates:
            similarity = max(0.0, 1.0 - dist)
            age_seconds = (now - mem.created_at).total_seconds() if mem.created_at else 0.0
            age_days = max(0.0, age_seconds / 86400.0)
            
            # Exponential decay: half-life of 14 days
            recency_decay = math.pow(2.0, - (age_days / half_life_days))
            final_score = similarity * recency_decay
            scored.append((final_score, mem.text_content))
            
        # Rank by final recency-weighted score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:limit]]
