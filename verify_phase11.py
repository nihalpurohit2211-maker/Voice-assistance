import asyncio
import websockets
import httpx
import uuid
import json

async def verify():
    print("Running Phase 11 verification...")
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as client:
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. 422 for malformed body
        resp = await client.post("/chat", headers=headers, json={"bad_key": "val"})
        assert resp.status_code == 422
        
        # 2. 401 for bad token
        resp = await client.get("/me", headers={"Authorization": "Bearer badtoken"})
        assert resp.status_code == 401
        
        # 3. 1008 for bad WS token
        try:
            async with websockets.connect("ws://localhost:8000/ws/voice?token=badtoken") as ws:
                assert False, "Should not connect"
        except websockets.exceptions.InvalidStatusCode as e:
            assert e.status_code in (401, 403), "Should get 401 or 403 from server"
        except websockets.exceptions.ConnectionClosedError as e:
            assert e.code == 1008
        
        print("Phase 11 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
