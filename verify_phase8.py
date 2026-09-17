import asyncio
import base64
from backend.services.tts_client import stream_speech
import time

async def verify():
    print("Running Phase 8 verification...")
    chunks = []
    
    start = time.time()
    
    async for chunk in stream_speech("Hello, this is a streaming test of the Cartesia TTS system."):
        print(f"Received chunk after {time.time() - start:.2f}s, size {len(chunk)} chars (base64)")
        chunks.append(base64.b64decode(chunk))
        start = time.time()
        
    assert len(chunks) > 1, "Should have received multiple chunks"
    
    full_audio = b"".join(chunks)
    assert len(full_audio) > 1000, "Audio bytes too small"
    
    with open("test_stream.raw", "wb") as f:
        f.write(full_audio)
        
    print(f"Phase 8 verification successful. Saved {len(full_audio)} bytes to test_stream.raw")

if __name__ == "__main__":
    asyncio.run(verify())
