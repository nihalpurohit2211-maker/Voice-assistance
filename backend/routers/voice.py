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
    session_history = []

    cartesia = None
    try:
        if settings.CARTESIA_API_KEY:
            from backend.services.tts_client import CartesiaSession
            cartesia = CartesiaSession()
            await cartesia.connect()
    except Exception as e:
        logger.warning(f"Cartesia init skipped or failed: {e}")

    async def run_turn(text: str, use_cartesia: bool, interrupt_event: asyncio.Event, turn_state: dict, mode_override: str = None, guidance_mode: str = None):
        try:
            t0 = time.time()
            logger.info(f"VOICE_TURN_START: {t0}")
            
            parsed_intent_val = "small_talk"
            active_mode_val = mode_override or "casual"
            
            if mode_override and cartesia:
                cartesia.set_mode(mode_override)

            def handle_intent(intent: str, mode: str = None):
                nonlocal parsed_intent_val, active_mode_val
                parsed_intent_val = intent
                active_mode_val = mode_override if mode_override else (mode or "casual")
                if cartesia:
                    cartesia.set_mode(active_mode_val)
                    
            _, text_gen = await run_pipeline_streaming(
                user_id, 
                text, 
                session_id=session_id, 
                history=session_history[-6:],
                mode_override=mode_override,
                guidance_mode=guidance_mode,
                on_intent_parsed=handle_intent
            )
            
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
                        ttfb = t1 - t0
                        logger.info(f"FIRST_TOKEN_RECEIVED: {t1} (Delay: {ttfb:.3f}s)")
                        first_token_received = True
                        
                        # Send metrics to frontend
                        asyncio.create_task(websocket.send_text(json.dumps({
                            "type": "metrics",
                            "ttfb": round(ttfb, 2),
                            "intent": parsed_intent_val,
                            "mode": active_mode_val
                        })))
                        
                    full_reply += chunk
                    sentence_buffer += chunk
                    
                    # Primary split: full sentence boundary [.?!] or newline
                    match = re.search(r'([.?!]+(?:\s+|$))|\n+', sentence_buffer)
                    # Do NOT split on commas or spaces under normal conditions, so prosody and speech remain natural!
                    # Only fallback on clause boundary if sentence is exceptionally long (> 280 chars) without terminal punctuation
                    if not match and len(sentence_buffer) > 280:
                        match = re.search(r'([;:]\s+)', sentence_buffer)
                    if not match and len(sentence_buffer) > 340:
                        match = re.search(r'(,\s+)', sentence_buffer)
                        
                    if match:
                        split_idx = match.end()
                        sentence = sentence_buffer[:split_idx].strip()
                        sentence_buffer = sentence_buffer[split_idx:]
                        if sentence:
                            yield sentence
                    elif len(sentence_buffer) > 400:
                        # Extreme fallback only if an LLM outputs 400+ chars with zero punctuation
                        last_space = sentence_buffer.rfind(' ')
                        if last_space > 150:
                            split_idx = last_space + 1
                            sentence = sentence_buffer[:split_idx].strip()
                            sentence_buffer = sentence_buffer[split_idx:]
                            if sentence:
                                yield sentence
                            
                if not interrupt_event.is_set() and sentence_buffer.strip():
                    yield sentence_buffer.strip()

            if use_cartesia and cartesia and getattr(cartesia, 'connected', False):
                # Pass the sentence generator to CartesiaSession
                async for chunk_text, audio_b64 in cartesia.stream_turn(sentence_generator(), interrupt_event):
                    if interrupt_event.is_set():
                        break
                    await websocket.send_text(json.dumps({
                        "type": "reply_chunk",
                        "text": chunk_text,
                        "audio": audio_b64
                    }))
            else:
                # Bypass Cartesia completely
                async for chunk_text in sentence_generator():
                    if interrupt_event.is_set():
                        break
                    if chunk_text.strip():
                        await websocket.send_text(json.dumps({
                            "type": "reply_chunk",
                            "text": chunk_text,
                            "audio": ""
                        }))
                            
            if not interrupt_event.is_set():
                turn_state["completed"] = True
                await websocket.send_text(json.dumps({"type": "turn_end"}))
                
                session_history.append({"role": "user", "content": text})
                session_history.append({"role": "assistant", "content": full_reply})
                
                async with async_session_maker() as db:
                    user_msg = ChatMessage(session_id=session_id, role="user", content=text, intent=parsed_intent_val)
                    asst_msg = ChatMessage(session_id=session_id, role="assistant", content=full_reply, was_interrupted=False)
                    db.add(user_msg)
                    db.add(asst_msg)
                    await db.commit()
                    
                asyncio.create_task(extract_memory_from_exchange(user_id, text, full_reply))
            else:
                spoken_offset = turn_state.get("spoken_offset", len(full_reply))
                truncated_reply = full_reply[:spoken_offset]
                
                session_history.append({"role": "user", "content": text})
                session_history.append({"role": "assistant", "content": truncated_reply})
                
                async with async_session_maker() as db:
                    user_msg = ChatMessage(session_id=session_id, role="user", content=text, intent=parsed_intent_val)
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
                use_cartesia = msg.get("use_cartesia", True)
                mode = msg.get("mode")
                guidance_mode = msg.get("guidance_mode")
                
                if current_turn_task and not current_turn_task.done():
                    interrupt_event.set()
                    
                interrupt_event = asyncio.Event()
                turn_state = {"completed": False, "spoken_offset": 0}
                current_turn_task = asyncio.create_task(run_turn(text, use_cartesia, interrupt_event, turn_state, mode_override=mode, guidance_mode=guidance_mode))
                
            elif msg.get("type") == "interrupt":
                if current_turn_task and not current_turn_task.done():
                    if not turn_state.get("completed"):
                        turn_state["spoken_offset"] = msg.get("spoken_offset", 0)
                        interrupt_event.set()
                        
            elif msg.get("type") == "replay_turn":
                text_to_replay = msg.get("text", "")
                use_cartesia = msg.get("use_cartesia", True)
                
                if current_turn_task and not current_turn_task.done():
                    interrupt_event.set()
                    
                interrupt_event = asyncio.Event()
                turn_state = {"completed": False, "spoken_offset": 0}
                
                async def run_replay_task():
                    async def replay_generator():
                        parts = re.split(r'([.?!]\s+|\n)', text_to_replay)
                        sentence_buf = ""
                        for p in parts:
                            sentence_buf += p
                            if re.search(r'[.?!]\s+|\n', p) or len(sentence_buf) > 280:
                                if sentence_buf.strip():
                                    yield sentence_buf.strip()
                                sentence_buf = ""
                        if sentence_buf.strip():
                            yield sentence_buf.strip()
                            
                    if use_cartesia:
                        async for chunk_text, audio_b64 in cartesia.stream_turn(replay_generator(), interrupt_event):
                            if interrupt_event.is_set():
                                break
                            await websocket.send_text(json.dumps({
                                "type": "reply_chunk",
                                "text": chunk_text,
                                "audio": audio_b64
                            }))
                    else:
                        async for s in replay_generator():
                            if interrupt_event.is_set():
                                break
                            await websocket.send_text(json.dumps({
                                "type": "reply_chunk",
                                "text": s,
                                "audio": ""
                            }))
                            
                    if not interrupt_event.is_set():
                        turn_state["completed"] = True
                        await websocket.send_text(json.dumps({"type": "turn_end"}))
                        
                current_turn_task = asyncio.create_task(run_replay_task())
                        
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
