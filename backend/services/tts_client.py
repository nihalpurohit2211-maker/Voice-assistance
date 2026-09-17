import httpx
import logging
import json
import websockets
import asyncio
import uuid
from backend.core.config import settings

logger = logging.getLogger(__name__)

class CartesiaSession:
    def __init__(self, voice_id: str = "a0e99841-438c-4a64-b679-ae501e7d6091"):
        if not settings.CARTESIA_API_KEY:
            raise ValueError("CARTESIA_API_KEY not set")
        self.api_key = settings.CARTESIA_API_KEY
        self.voice_id = voice_id
        self.ws = None
        self.connected = False
        self._lock = asyncio.Lock()

    async def connect(self):
        url = "wss://api.cartesia.ai/tts/websocket?cartesia_version=2024-06-10"
        headers = {
            "X-API-Key": self.api_key,
            "Cartesia-Version": "2024-06-10"
        }
        try:
            self.ws = await websockets.connect(url, extra_headers=headers)
            self.connected = True
            logger.info("Cartesia WebSocket connected.")
        except Exception as e:
            logger.error(f"Failed to connect to Cartesia: {e}")
            self.connected = False

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.connected = False
            logger.info("Cartesia WebSocket closed.")

    async def _ensure_connected(self):
        async with self._lock:
            if not self.connected or (self.ws and self.ws.closed):
                logger.warning("Cartesia connection lost. Reconnecting...")
                await self.connect()

    async def stream_turn(self, text_chunk_gen, interrupt_event: asyncio.Event):
        """
        Streams a turn consisting of multiple text chunks (sentences) over the same connection.
        Returns an async generator of (chunk_text, audio_b64).
        """
        await self._ensure_connected()
        if not self.connected:
            return

        context_id = str(uuid.uuid4())
        text_queue = asyncio.Queue()
        
        # 1. Start a background task to pump chunks to Cartesia
        async def pump_text():
            try:
                first = True
                async for chunk in text_chunk_gen:
                    if interrupt_event.is_set():
                        break
                    
                    if not chunk.strip():
                        continue
                        
                    await text_queue.put(chunk)
                    
                    payload = {
                        "context_id": context_id,
                        "transcript": chunk + " ",
                        "continue": True,
                        "model_id": "sonic-latest",
                        "voice": {"mode": "id", "id": self.voice_id},
                        "output_format": {
                            "container": "raw",
                            "encoding": "pcm_s16le",
                            "sample_rate": 24000
                        }
                    }
                    first = False
                        
                    await self._ensure_connected()
                    if self.connected:
                        await self.ws.send(json.dumps(payload))
                        
                # End of turn
                if self.connected and not interrupt_event.is_set() and not first:
                    await self.ws.send(json.dumps({
                        "context_id": context_id,
                        "transcript": "",
                        "continue": False,
                        "model_id": "sonic-latest",
                        "voice": {"mode": "id", "id": self.voice_id},
                        "output_format": {
                            "container": "raw",
                            "encoding": "pcm_s16le",
                            "sample_rate": 24000
                        }
                    }))
            except Exception as e:
                logger.error(f"Error pumping text to Cartesia: {e}")

        pump_task = asyncio.create_task(pump_text())

        # 2. Read audio chunks back
        try:
            while True:
                if interrupt_event.is_set():
                    break
                    
                msg = await self.ws.recv()
                data = json.loads(msg)
                
                if data.get("context_id") == context_id:
                    if data.get("type") == "chunk":
                        chunk_text = ""
                        try:
                            chunk_text = text_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                            
                        yield chunk_text, data.get("data")
                    elif data.get("type") == "done":
                        break
                    elif data.get("type") == "error":
                        logger.error(f"Cartesia error: {data}")
                        break
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Cartesia connection closed mid-stream.")
            self.connected = False
        except Exception as e:
            logger.error(f"Error reading from Cartesia: {e}")
            if self.ws and self.ws.closed:
                self.connected = False
        finally:
            if not pump_task.done():
                pump_task.cancel()

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
