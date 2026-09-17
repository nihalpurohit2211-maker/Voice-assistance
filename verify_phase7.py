import asyncio
import httpx
import uuid

async def verify():
    print("Running Phase 6/7 verification...")
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("Sending first message...")
        await client.post("/chat", headers=headers, json={"message": "I love eating pizza on Fridays."})
        
        print("Sending second message...")
        resp = await client.post("/chat", headers=headers, json={"message": "What do you remember about me?"})
        reply = resp.json()
        
        # safely encode print for Windows
        print("Reply:", reply["reply"].encode('ascii', 'ignore').decode())
        assert "pizza" in reply["reply"].lower() or "friday" in reply["reply"].lower()
        
        resp = await client.get("/chats", headers=headers)
        assert len(resp.json()) == 0
        
        print("Phase 6 and 7 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
