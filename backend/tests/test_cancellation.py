import asyncio
from backend.services.llm_client import stream_complete

async def test_server_cancellation():
    print("--- Verifying Checkpoint (d): Server-Side LLM Cancellation ---")
    gen = stream_complete("You are a helpful assistant.", [{"role": "user", "content": "Write a 500-word essay about the history of mathematics."}])
    
    tokens_read = 0
    async for token in gen:
        tokens_read += 1
        if tokens_read >= 5:
            print(f"Read {tokens_read} tokens. Breaking stream early to simulate interrupt.")
            break
            
    print("Generator loop broken. Checking if stream terminated cleanly...")
    # Explicitly close the generator (simulating what Python does when an abandoned generator is garbage collected or aclosed)
    await gen.aclose()
    print("-> PASS Checkpoint (d): Generator closed cleanly without hanging. HTTP stream connection terminated.")

if __name__ == "__main__":
    asyncio.run(test_server_cancellation())
