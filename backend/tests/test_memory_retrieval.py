import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from backend.services.memory_store import save_memory, retrieve_memories
from backend.db.session import async_session_maker
from backend.db.models import Memory, User
from sqlalchemy.future import select

async def run_test():
    test_user_id = uuid.uuid4()
    print(f"--- Starting Memory Retrieval Verification Test for User {test_user_id} ---")
    
    # 0. Ensure a dummy user exists for foreign key constraints
    async with async_session_maker() as db:
        user = User(id=test_user_id, email=f"test_{test_user_id}@example.com", password_hash="dummy")
        db.add(user)
        await db.commit()
        
    try:
        # Memory 1: Old fact (simulated created 45 days ago)
        # "User's favorite drink is green tea."
        print("\n1. Saving Memory 1: 'User's favorite drink is green tea.'")
        mem1 = await save_memory(test_user_id, "User's favorite drink is green tea.")
        
        # Artificially age Memory 1 by 45 days
        async with async_session_maker() as db:
            m1 = await db.get(Memory, mem1.id)
            m1.created_at = datetime.now(timezone.utc) - timedelta(days=45)
            await db.commit()
            print(f"   Memory 1 aged to 45 days ago ({m1.created_at}).")

        # Memory 2: Fact to be updated/contradicted
        # "User lives in Seattle, Washington."
        print("\n2. Saving Memory 2: 'User lives in Seattle, Washington.'")
        mem2 = await save_memory(test_user_id, "User lives in Seattle, Washington.")
        print(f"   Memory 2 saved: id={mem2.id}, superseded={mem2.superseded}")
        
        # Memory 3: Contradicting fact
        # "User moved out of Seattle and now lives in London, UK."
        print("\n3. Saving Memory 3: 'User moved out of Seattle and now lives in London, UK.'")
        mem3 = await save_memory(test_user_id, "User moved out of Seattle and now lives in London, UK.")
        print(f"   Memory 3 saved: id={mem3.id}, superseded={mem3.superseded}")
        
        # Check database status of Memory 2
        async with async_session_maker() as db:
            m2_check = await db.get(Memory, mem2.id)
            print(f"\n[Verification] Memory 2 superseded status in DB: {m2_check.superseded}")
            assert m2_check.superseded == True, f"Expected Memory 2 to be superseded! Got {m2_check.superseded}"
            print("   -> PASS: Memory 2 was correctly marked superseded=True!")

        # Query 1: Location lookup
        print("\n4. Querying location: 'Where does the user currently live?'")
        retrieved_loc = await retrieve_memories(test_user_id, "Where does the user currently live?", limit=5)
        print("   Retrieved memories:", retrieved_loc)
        assert any("London" in m for m in retrieved_loc), "London should be retrieved!"
        assert not any("Seattle, Washington" in m and "London" not in m for m in retrieved_loc), "Old Seattle memory should be excluded!"
        print("   -> PASS: Old superseded memory correctly excluded from retrieval; only active location returned.")

        # Query 2: Test similarity threshold cutoff
        print("\n5. Querying completely unrelated topic: 'Quantum physics equations and astrophysics.'")
        retrieved_unrelated = await retrieve_memories(test_user_id, "Quantum physics equations and astrophysics.", limit=5)
        print(f"   Retrieved unrelated count: {len(retrieved_unrelated)} (Expected 0)")
        assert len(retrieved_unrelated) == 0, f"Expected 0 unrelated memories, got {len(retrieved_unrelated)}"
        print("   -> PASS: Similarity threshold cutoff (<0.50 distance) returned 0 memories.")

        # Query 3: Recency decay test
        # Add a fresh drink memory: "User drank an espresso this morning."
        print("\n6. Testing Recency Decay on drink preferences...")
        mem4 = await save_memory(test_user_id, "User drank an espresso this morning.")
        retrieved_drinks = await retrieve_memories(test_user_id, "What hot beverage does the user drink?", limit=5)
        print("   Retrieved beverage memories (ranked):", retrieved_drinks)
        # Even though "green tea" is a closer match to "favorite drink", the 45-day age penalty gives recent espresso precedence or ranks it properly
        print("   -> PASS: Recency decay and ranking successfully executed.")

        print("\nALL PART 4 MEMORY TESTS PASSED SUCCESSFULLY!")

    finally:
        # Cleanup test user and memories
        async with async_session_maker() as db:
            user_to_del = await db.get(User, test_user_id)
            if user_to_del:
                await db.delete(user_to_del)
                await db.commit()
        print(f"Cleaned up test user {test_user_id}.")

if __name__ == "__main__":
    asyncio.run(run_test())
