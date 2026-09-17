
import asyncio
import time
import uuid
from backend.services.memory_store import retrieve_memories
from backend.services.embeddings import embed
from backend.db.session import async_session_maker
from backend.db.models import Memory
from sqlalchemy.future import select

async def main():
    user_id = uuid.uuid4()
    query_embedding = embed("Hello!")
    
    for i in range(2):
        async with async_session_maker() as db:
            t3 = time.time()
            stmt = select(Memory.text_content).where(Memory.user_id == user_id).limit(5)
            result = await db.execute(stmt)
            list(result.scalars().all())
            print(f"Iter {i} DB Query took {time.time() - t3:.3f}s")

if __name__ == "__main__":
    asyncio.run(main())

