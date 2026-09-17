import asyncio
import httpx
import uuid

async def verify():
    email = f"test_{uuid.uuid4().hex[:6]}@test.com"
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # Register
        resp = await client.post("/auth/register", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 200, f"Register failed: {resp.text}"
        token = resp.json()["token"]
        assert token

        # Login
        resp = await client.post("/auth/login", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        assert resp.json()["token"]

        # Get me
        resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Get me failed: {resp.text}"
        user_data = resp.json()
        assert user_data["email"] == email

        # Unauthorized Get me
        resp = await client.get("/me")
        assert resp.status_code in [403, 401], f"Unauthorized failed: {resp.status_code}"

        print("Phase 2 verification successful")

if __name__ == "__main__":
    asyncio.run(verify())
