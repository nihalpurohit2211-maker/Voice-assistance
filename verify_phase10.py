import asyncio
import websockets
import httpx
import uuid
import json

async def verify():
    print("Running Phase 10 verification...")
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        async with websockets.connect(f"ws://localhost:8000/ws/voice?token={token}") as ws:
            await ws.send(json.dumps({"type": "user_turn", "text": "Tell me a long story about space."}))
            
            msg = json.loads(await ws.recv())
            assert msg["type"] == "reply_chunk"
            
            await ws.send(json.dumps({"type": "interrupt", "spoken_offset": 20}))
            
            while True:
                try:
                    msg_str = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(msg_str)
                    if msg["type"] == "turn_end":
                        assert False, "Should not receive turn_end after interrupt"
                except asyncio.TimeoutError:
                    break
        
        await asyncio.sleep(0.5)
        
        resp = await client.get("/chats", headers=headers)
        sessions = resp.json()
        assert len(sessions) == 1
        session_id = sessions[0]["id"]
        
        resp = await client.get(f"/chats/{session_id}", headers=headers)
        session_details = resp.json()
        messages = session_details["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["was_interrupted"] is True
        assert len(messages[1]["content"]) <= 20
        
        print("Phase 10 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
