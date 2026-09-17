import asyncio
import socket

_orig_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if "neon.tech" in host:
        return _orig_getaddrinfo("52.95.251.153", port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from backend.core.config import settings

async def test_db():
    print(f"Connecting to database...")
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Connected! Creating vector extension if not exists...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        print("Vector extension verified.")
    await engine.dispose()
    print("Database connection test successful.")

if __name__ == "__main__":
    asyncio.run(test_db())
