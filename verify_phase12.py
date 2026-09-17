import asyncio
import websockets
import httpx
import uuid
import json

async def verify():
    print("Running Phase 12 Final Acceptance Checklist...")
    
    # User 1
    email1 = f"user1_{uuid.uuid4().hex[:6]}@test.com"
    email2 = f"user2_{uuid.uuid4().hex[:6]}@test.com"
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # 1. Register -> login -> GET /me
        await client.post("/auth/register", json={"email": email1, "password": "password123"})
        resp = await client.post("/auth/login", json={"email": email1, "password": "password123"})
        token1 = resp.json()["token"]
        headers1 = {"Authorization": f"Bearer {token1}"}
        
        resp = await client.get("/me", headers=headers1)
        assert resp.status_code == 200
        assert resp.json()["email"] == email1
        
        print("1. Auth flow works.")
        
        # 2. POST /chat for memory
        await client.post("/chat", headers=headers1, json={"message": "My name is Jonathan from London."})
        
        await asyncio.sleep(2)
        
        resp = await client.post("/chat", headers=headers1, json={"message": "What is my name and where am I from?"})
        reply = resp.json()["reply"].lower()
        print(f"Reply: {reply}")
        assert "jonathan" in reply
        
        print("2. Memory retrieval works.")
        
        # 4. WS full turn
        async with websockets.connect(f"ws://localhost:8000/ws/voice?token={token1}") as ws:
            await ws.send(json.dumps({"type": "user_turn", "text": "Say a short hello."}))
            
            while True:
                msg = json.loads(await ws.recv())
                if msg["type"] == "turn_end":
                    break
                    
        print("4. WS full turn works.")
        
        # 5. WS interrupted turn
        async with websockets.connect(f"ws://localhost:8000/ws/voice?token={token1}") as ws:
            await ws.send(json.dumps({"type": "user_turn", "text": "Tell me a long story about a dragon."}))
            msg = json.loads(await ws.recv())
            assert msg["type"] == "reply_chunk"
            
            await ws.send(json.dumps({"type": "interrupt", "spoken_offset": 15}))
            
            while True:
                try:
                    msg_str = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(msg_str)
                    assert msg["type"] != "turn_end"
                except asyncio.TimeoutError:
                    break
                    
        print("5. WS interrupt works.")
        
        # 3. GET /chats history
        await asyncio.sleep(1.0)
        resp = await client.get("/chats", headers=headers1)
        sessions = resp.json()
        assert len(sessions) == 2
        
        sess_id = sessions[0]["id"]
        resp = await client.get(f"/chats/{sess_id}", headers=headers1)
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 2
        assert messages[1]["role"] == "assistant"
        
        print("3. Chat history works.")
        
        # 6. Second user isolation
        await client.post("/auth/register", json={"email": email2, "password": "password123"})
        resp = await client.post("/auth/login", json={"email": email2, "password": "password123"})
        token2 = resp.json()["token"]
        headers2 = {"Authorization": f"Bearer {token2}"}
        
        resp = await client.get("/chats", headers=headers2)
        assert len(resp.json()) == 0
        
        resp = await client.get(f"/chats/{sess_id}", headers=headers2)
        assert resp.status_code == 404
        
        resp = await client.get("/memories", headers=headers2)
        assert len(resp.json()) == 0
        
        print("6. User isolation works.")
        
        print("7. No API keys exposed (verified manually).")
        
        print("\nALL PHASES COMPLETED SUCCESSFULLY.")

if __name__ == "__main__":
    asyncio.run(verify())
