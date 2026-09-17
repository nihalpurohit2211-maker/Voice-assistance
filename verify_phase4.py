import asyncio
import httpx
import uuid
from backend.services.memory_store import save_memory

async def verify():
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        token = resp.json()["token"]
        
        resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id_str = resp.json()["user_id"]
        user_id = uuid.UUID(user_id_str)
        
        await save_memory(user_id, "user likes hiking")
        
        resp = await client.get("/memories", headers={"Authorization": f"Bearer {token}"})
        memories = resp.json()
        assert len(memories) == 1
        assert memories[0]["text"] == "user likes hiking"
        mem_id = memories[0]["id"]
        
        resp = await client.delete(f"/memories/{mem_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        
        resp = await client.get("/memories", headers={"Authorization": f"Bearer {token}"})
        assert len(resp.json()) == 0
        
        resp_b = await client.post("/auth/register", json={"email": f"b_{email}", "password": "testpass123"})
        token_b = resp_b.json()["token"]
        
        await save_memory(user_id, "user A's secret")
        
        resp = await client.get("/memories", headers={"Authorization": f"Bearer {token}"})
        mem_id_2 = resp.json()[0]["id"]
        
        resp_del_b = await client.delete(f"/memories/{mem_id_2}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_del_b.status_code == 404
        
        print("Phase 4 verification successful")

if __name__ == "__main__":
    asyncio.run(verify())
