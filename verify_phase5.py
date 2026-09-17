import asyncio
import uuid
from backend.services.pipeline import run_pipeline
from backend.services.memory_store import retrieve_memories
from backend.db.session import async_session_maker
from backend.db.models import User
from sqlalchemy.future import select

async def verify():
    print("Running Phase 5 verification...")
    user_id = uuid.uuid4()
    
    async with async_session_maker() as db:
        new_user = User(id=user_id, email=f"test_{user_id.hex[:6]}@test.com", password_hash="hash")
        db.add(new_user)
        await db.commit()
    
    result = await run_pipeline(user_id, "I just moved to Mumbai for a new job.")
    print("Pipeline result:", result)
    
    assert "reply" in result
    assert "intent" in result
    assert result["intent"] in ["small_talk", "question", "instruction", "emotional"]
    
    memories = await retrieve_memories(user_id, "Mumbai job", limit=5)
    print("Extracted memories:", memories)
    assert len(memories) >= 1
    assert any("Mumbai" in m or "job" in m for m in memories)
    
    print("Phase 5 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
