import asyncio
import json
import uuid
import re
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.future import select
from datetime import datetime, timezone

from backend.db.session import async_session_maker
from backend.db.models import ChatSession, ChatMessage
from backend.core.security import decode_access_token
from backend.services.pipeline import run_pipeline_streaming, extract_memory_from_exchange

import logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket, token: str):
    decoded = decode_access_token(token)
    if not decoded or "sub" not in decoded:
        await websocket.close(code=1008)
        return
        
    user_id_str = decoded["sub"]
    user_id = uuid.UUID(user_id_str)
    
    await websocket.accept()
    
    async with async_session_maker() as db:
        session = ChatSession(user_id=user_id)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id

    current_turn_task = None
    interrupt_event = None
    turn_state = {}

    from backend.services.tts_client import CartesiaSession
    cartesia = CartesiaSession()
    await cartesia.connect()

    async def run_turn(text: str, interrupt_event: asyncio.Event, turn_state: dict):
        try:
            t0 = time.time()
            logger.info(f"VOICE_TURN_START: {t0}")
            
            intent, text_gen = await run_pipeline_streaming(user_id, text)
            
            full_reply = ""
            first_token_received = False
            
            # Create a generator for sentence boundaries
            async def sentence_generator():
                nonlocal full_reply, first_token_received
                sentence_buffer = ""
                
                async for chunk in text_gen:
                    if interrupt_event.is_set():
                        break
                        
                    if not first_token_received and chunk.strip():
                        t1 = time.time()
                        logger.info(f"FIRST_TOKEN_RECEIVED: {t1} (Delay: {t1 - t0:.3f}s)")
                        first_token_received = True
                        
                    full_reply += chunk
                    sentence_buffer += chunk
                    
                    match = re.search(r'([.?!]\s+|\n)', sentence_buffer)
                    if match or len(sentence_buffer) > 150:
                        split_idx = match.end() if match else len(sentence_buffer)
                        sentence = sentence_buffer[:split_idx].strip()
                        sentence_buffer = sentence_buffer[split_idx:]
                        
                        if sentence:
                            yield sentence
                            
                if not interrupt_event.is_set() and sentence_buffer.strip():
                    yield sentence_buffer.strip()

            # Pass the sentence generator to CartesiaSession
            async for chunk_text, audio_b64 in cartesia.stream_turn(sentence_generator(), interrupt_event):
                if interrupt_event.is_set():
                    break
                await websocket.send_text(json.dumps({
                    "type": "reply_chunk",
                    "text": chunk_text,
                    "audio": audio_b64
                }))
                            
            if not interrupt_event.is_set():
                turn_state["completed"] = True
                await websocket.send_text(json.dumps({"type": "turn_end"}))
                
                async with async_session_maker() as db:
                    user_msg = ChatMessage(session_id=session_id, role="user", content=text, intent=intent)
                    asst_msg = ChatMessage(session_id=session_id, role="assistant", content=full_reply, was_interrupted=False)
                    db.add(user_msg)
                    db.add(asst_msg)
                    await db.commit()
                    
                asyncio.create_task(extract_memory_from_exchange(user_id, text, full_reply))
            else:
                spoken_offset = turn_state.get("spoken_offset", len(full_reply))
                truncated_reply = full_reply[:spoken_offset]
                
                async with async_session_maker() as db:
                    user_msg = ChatMessage(session_id=session_id, role="user", content=text, intent=intent)
                    asst_msg = ChatMessage(session_id=session_id, role="assistant", content=truncated_reply, was_interrupted=True)
                    db.add(user_msg)
                    db.add(asst_msg)
                    await db.commit()
                    
        except Exception as e:
            if not interrupt_event.is_set():
                import traceback
                traceback.print_exc()
                try:
                    await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                except Exception:
                    pass

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
                
            if msg.get("type") == "user_turn":
                text = msg.get("text", "")
                
                if current_turn_task and not current_turn_task.done():
                    interrupt_event.set()
                    
                interrupt_event = asyncio.Event()
                turn_state = {"completed": False, "spoken_offset": 0}
                current_turn_task = asyncio.create_task(run_turn(text, interrupt_event, turn_state))
                
            elif msg.get("type") == "interrupt":
                if current_turn_task and not current_turn_task.done():
                    if not turn_state.get("completed"):
                        turn_state["spoken_offset"] = msg.get("spoken_offset", 0)
                        interrupt_event.set()
                        
    except WebSocketDisconnect:
        pass
    finally:
        if current_turn_task and not current_turn_task.done():
            interrupt_event.set()
            
        await cartesia.close()
            
        async with async_session_maker() as db:
            result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
            sess = result.scalars().first()
            if sess:
                sess.ended_at = datetime.now(timezone.utc)
                await db.commit()
