import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from backend.core.config import settings

async def verify_phase1():
    print("Connecting to database for Phase 1 verification...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Check tables exist
        tables = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        table_names = [r[0] for r in tables.fetchall()]
        print(f"Tables found: {table_names}")
        assert 'users' in table_names
        assert 'memories' in table_names
        assert 'chat_sessions' in table_names
        assert 'chat_messages' in table_names

        # Insert test user
        print("Inserting test user...")
        await conn.execute(text("INSERT INTO users (email, password_hash) VALUES ('test@verify.com', 'hash123')"))
        
        # Query it back
        res = await conn.execute(text("SELECT email FROM users WHERE email='test@verify.com'"))
        user = res.fetchone()
        assert user is not None and user[0] == 'test@verify.com'
        print("Test user inserted and queried successfully.")

        # Delete test user
        await conn.execute(text("DELETE FROM users WHERE email='test@verify.com'"))
        print("Test user deleted.")
        
    await engine.dispose()
    print("Phase 1 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify_phase1())
