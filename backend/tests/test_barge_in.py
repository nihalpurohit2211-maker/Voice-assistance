import asyncio
import json
import uuid
from starlette.testclient import TestClient
from backend.main import app
from backend.core.security import create_access_token
from backend.db.session import async_session_maker
from backend.db.models import User, ChatSession, ChatMessage
from sqlalchemy.future import select

def test_barge_in_sync():
    print("=== Testing Barge-In End-to-End via ASGI In-Process TestClient ===")
    test_user_id = uuid.uuid4()
    
    # Setup test user in database
    async def setup():
        async with async_session_maker() as db:
            user = User(id=test_user_id, email=f"bargein_{test_user_id}@example.com", password_hash="dummy")
            db.add(user)
            await db.commit()
    asyncio.run(setup())
    print(f"Created test user: {test_user_id}")

    token = create_access_token({"sub": str(test_user_id)})
    client = TestClient(app)
    
    received_chunks = []
    interrupt_sent = False
    target_offset = 25  # simulate client hearing 25 characters before interrupting
    
    try:
        with client.websocket_connect(f"/ws/voice?token={token}") as ws:
            print("Connected to /ws/voice WebSocket.")
            
            # Send a user turn that requests a detailed answer
            user_turn_msg = {
                "type": "user_turn",
                "text": "Tell me a story about a quiet mountain with several sentences.",
                "use_cartesia": False  # Test clean text streaming pipeline
            }
            ws.send_text(json.dumps(user_turn_msg))
            print("Sent user turn message.")
            
            # Receive chunks
            while True:
                data = ws.receive_text()
                msg = json.loads(data)
                msg_type = msg.get("type")
                
                if msg_type == "reply_chunk":
                    chunk_text = msg.get("text", "")
                    received_chunks.append(chunk_text)
                    print(f"Received chunk ({len(chunk_text)} chars): '{chunk_text[:30]}...'")
                    
                    # Once we have received at least 1 chunk, trigger barge-in mid-sentence!
                    if not interrupt_sent:
                        print(f"\n---> Triggering Barge-in interrupt with spoken_offset={target_offset} <---")
                        interrupt_msg = {
                            "type": "interrupt",
                            "spoken_offset": target_offset
                        }
                        ws.send_text(json.dumps(interrupt_msg))
                        interrupt_sent = True
                        break

            # Now test replay_turn with full text
            print("\n--- Testing Replay Turn ('continue') ---")
            full_text_to_replay = "There is a quiet mountain where the morning mist lingers softly."
            ws.send_text(json.dumps({
                "type": "replay_turn",
                "text": full_text_to_replay,
                "use_cartesia": False
            }))
            
            replayed_chunks = []
            while True:
                data = ws.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "reply_chunk":
                    replayed_chunks.append(msg.get("text", ""))
                elif msg.get("type") == "turn_end":
                    break
                    
            print(f"Replay received {len(replayed_chunks)} chunks: {' '.join(replayed_chunks)}")
            assert any("quiet mountain" in c for c in replayed_chunks), "Replayed text must contain original sentence!"
            print("-> PASS: Replay successfully streamed the original text without calling the LLM!")

        print(f"\nTotal chunks received by client before interrupt: {len(received_chunks)}")
        
        # Give DB commit a brief moment
        async def check_db():
            async with async_session_maker() as db:
                res = await db.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                    .where(ChatSession.user_id == test_user_id, ChatMessage.role == "assistant")
                )
                asst_msg = res.scalars().first()
                return asst_msg
                
        asst_msg = asyncio.run(check_db())
        print("\n--- Verifying Checkpoint (c) in Database ---")
        if asst_msg:
            print(f"Stored assistant message in DB:")
            print(f"  - was_interrupted: {asst_msg.was_interrupted}")
            print(f"  - content length: {len(asst_msg.content)}")
            print(f"  - content: '{asst_msg.content}'")
            assert asst_msg.was_interrupted == True, "Expected was_interrupted to be True!"
            assert len(asst_msg.content) <= target_offset, f"Expected content length <= {target_offset}, got {len(asst_msg.content)}"
            print(f"-> PASS Checkpoint (c): Assistant message correctly truncated to '{asst_msg.content}' and was_interrupted=True!")
        else:
            raise AssertionError("No assistant message found in DB!")

    finally:
        async def cleanup():
            async with async_session_maker() as db:
                user_to_del = await db.get(User, test_user_id)
                if user_to_del:
                    await db.delete(user_to_del)
                    await db.commit()
        asyncio.run(cleanup())
        print("Cleaned up test user.")

if __name__ == "__main__":
    test_barge_in_sync()
