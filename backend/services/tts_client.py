import httpx
import logging
import json
from backend.core.config import settings

logger = logging.getLogger(__name__)

async def stream_speech(text: str, voice_id: str = "a0e99841-438c-4a64-b679-ae501e7d6091"):
    if not settings.CARTESIA_API_KEY:
        raise ValueError("CARTESIA_API_KEY not set")
    
    headers = {
        "X-API-Key": settings.CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model_id": "sonic-latest",
        "transcript": text,
        "voice": {
            "mode": "id",
            "id": voice_id
        },
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 24000
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", "https://api.cartesia.ai/tts/sse", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data_json = json.loads(data_str)
                        if data_json.get("type") == "chunk" and data_json.get("data"):
                            yield data_json["data"]
                    except json.JSONDecodeError:
                        pass

async def generate_speech(text: str, voice_id: str = "a0e99841-438c-4a64-b679-ae501e7d6091") -> bytes:
    if not settings.CARTESIA_API_KEY:
        raise ValueError("CARTESIA_API_KEY not set")
    
    headers = {
        "X-API-Key": settings.CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model_id": "sonic-latest",
        "transcript": text,
        "voice": {
            "mode": "id",
            "id": voice_id
        },
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 24000
        }
    }
    
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api.cartesia.ai/tts/bytes", headers=headers, json=payload)
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPError as e:
            if attempt == 1:
                logger.error(f"Cartesia API call failed after 2 attempts: {e}")
                raise
            else:
                logger.warning(f"Cartesia API call failed, retrying: {e}")
