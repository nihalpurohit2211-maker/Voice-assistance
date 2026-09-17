import asyncio
from backend.services.tts_client import generate_speech
import os

async def verify():
    print("Running Phase 6 verification...")
    audio_bytes = await generate_speech("Hello, this is a test of the Cartesia TTS system.")
    
    assert isinstance(audio_bytes, bytes)
    assert len(audio_bytes) > 1000, "Audio bytes too small to be valid audio"
    
    with open("test_audio.wav", "wb") as f:
        f.write(audio_bytes)
        
    assert os.path.exists("test_audio.wav")
    print(f"Saved {len(audio_bytes)} bytes to test_audio.wav")
    print("Phase 6 verification successful.")

if __name__ == "__main__":
    asyncio.run(verify())
