import asyncio
import websockets
import httpx
import uuid
import json

async def verify():
    print("Running Phase 9 verification...")
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        async with websockets.connect(f"ws://localhost:8000/ws/voice?token={token}") as ws:
            await ws.send(json.dumps({"type": "user_turn", "text": "Tell me a short fact about space."}))
            
            chunks_received = 0
            while True:
                msg = json.loads(await ws.recv())
                if msg["type"] == "reply_chunk":
                    chunks_received += 1
                elif msg["type"] == "turn_end":
                    break
                elif msg["type"] == "error":
                    raise Exception(msg["message"])
                    
            assert chunks_received > 0, "No audio chunks received"
        
        # Give a tiny bit of time for finally block to update ended_at
        await asyncio.sleep(0.5)
        
        resp = await client.get("/chats", headers=headers)
        sessions = resp.json()
        assert len(sessions) == 1
        session_id = sessions[0]["id"]
        assert sessions[0]["ended_at"] is not None
        
        resp = await client.get(f"/chats/{session_id}", headers=headers)
        session_details = resp.json()
        messages = session_details["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        
        print("Phase 9 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
