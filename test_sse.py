import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        async with client.stream(
            'POST', 'https://api.cartesia.ai/tts/sse',
            headers={'X-API-Key': 'sk_car_Dfdj4VY9K7bHhu1mPpeaAT', 'Cartesia-Version': '2024-06-10', 'Content-Type': 'application/json'},
            json={
                'model_id': 'sonic-latest',
                'transcript': 'Hello world',
                'voice': {'mode': 'id', 'id': 'a0e99841-438c-4a64-b679-ae501e7d6091'},
                'output_format': {'container': 'raw', 'encoding': 'pcm_s16le', 'sample_rate': 8000}
            }
        ) as r:
            count = 0
            async for line in r.aiter_lines():
                if count > 5:
                    break
                print(line[:100])
                count += 1

asyncio.run(test())
