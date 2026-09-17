
import asyncio
import json
import time
import websockets
import httpx

async def test_live():
    # Login
    auth_url = "https://voice-assistance-whjo.onrender.com/auth/login"
    login_data = {"email": "test4@test.com", "password": "testpass123"}
    
    t0 = time.time()
    async with httpx.AsyncClient() as client:
        resp = await client.post(auth_url, json=login_data, timeout=30.0)
        token = resp.json().get("token")
        
    t1 = time.time()
    print(f"Login took {t1 - t0:.3f}s")
    
    ws_url = f"wss://voice-assistance-whjo.onrender.com/ws/voice?token={token}"
    async with websockets.connect(ws_url) as ws:
        t2 = time.time()
        print(f"WS Connect took {t2 - t1:.3f}s")
        
        await ws.send(json.dumps({"type": "audio_chunk", "data": "dummy_audio"}))
        await ws.send(json.dumps({"type": "turn_end"}))
        # It expects transcribe to happen but wait, we simulate by sending final transcript?
        # No, the backend expects whisper to transcribe. We can't fake that easily without audio.
        # Actually, in pipeline, it only responds when it gets text.
        # Can we send text directly?
        await ws.send(json.dumps({"type": "simulate_text", "text": "Hello!"}))

