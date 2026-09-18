import uuid
import logging
from backend.services.memory_store import retrieve_memories, save_memory
from backend.services.llm_client import complete

logger = logging.getLogger(__name__)

INTENT_PROMPT = """Classify the user's intent. Output exactly one word from this list and nothing else:
small_talk
question
instruction
emotional
playful"""

INTENT_TO_MODE = {
    "small_talk": "casual",
    "question": "focused",
    "instruction": "focused",
    "emotional": "reflective",
    "playful": "playful",
}

MODE_TONE_INSTRUCTIONS = {
    "casual": "TONE & STYLE (Casual Mode): Speak in a light, warm, and friendly tone. Keep it natural, relaxed, and conversational, like chatting with a good companion.",
    "focused": "TONE & STYLE (Focused Mode): Speak in a clear, efficient, and helpful tone. Prioritize getting to the point without excessive flourish or fluff, while maintaining warmth and clarity.",
    "reflective": "TONE & STYLE (Reflective Mode): Speak in a calm, comforting, and reassuring tone. Your presence is steady, kind, and patient. Listen deeply and offer thoughtful, grounded understanding.",
    "playful": "TONE & STYLE (Playful Mode): Speak in an energetic, playful, and witty tone. Bring humor, lightness, and lively enthusiasm to your answers.",
}

def get_system_prompt_for_mode(mode: str = "casual") -> str:
    tone_inst = MODE_TONE_INSTRUCTIONS.get(mode, MODE_TONE_INSTRUCTIONS["casual"])
    return f"""You are an advanced voice assistant operating in {mode.capitalize()} Mode.
{tone_inst}

CONVERSATIONAL CONTINUITY & RECENT CONTEXT:
Use the recent conversational history naturally. Reference previous statements where relevant, build directly upon the ongoing thread, and avoid repeating information you just said. Treat the conversation as a flowing dialogue.

ADAPTIVE RESPONSE LENGTH & ENERGY:
Match your response length and depth to the user's input:
- For short, casual, or brief inputs (e.g. "hey", "cool", "yeah", "thanks", "nice"), give a short, casual, and warm single-sentence reply. Do not default to full, multi-sentence paragraphs for brief comments.
- For detailed, emotionally expressive, or open-ended questions, provide a fuller, more thoughtful answer.
- Keep all spoken responses natural, unhurried, and conversational.

CONTEXT & MEMORIES:
Use the user's context and memories below to inform your response, but do not mention the memories directly unless relevant.

CRITICAL: Your response MUST start exactly with an intent tag in brackets, chosen from: [small_talk], [question], [instruction], [emotional], or [playful]. Immediately after the tag, provide your response.
Example: [small_talk] Take your time. I'm right here with you."""

SYSTEM_PROMPT = get_system_prompt_for_mode("reflective")

MEMORY_PROMPT = """Analyze the following exchange. Does it contain a persistent, factual piece of information about the user that is worth remembering long-term?
If yes, output a concise single sentence summarizing the fact.
If no, output exactly 'NO'."""

async def get_recent_session_messages(session_id: uuid.UUID, limit_turns: int = 3) -> list[dict]:
    """Fetch the last 2-3 turns (user + assistant pairs) for short-term working context."""
    if not session_id:
        return []
    try:
        from backend.db.models import ChatMessage
        from backend.db.session import async_session_maker
        from sqlalchemy.future import select
        
        async with async_session_maker() as db:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit_turns * 2)
            )
            result = await db.execute(stmt)
            messages = list(result.scalars().all())
            messages.reverse()
            return [{"role": m.role, "content": m.content} for m in messages]
    except Exception as e:
        logger.error(f"Error fetching session messages: {e}")
        return []

async def run_pipeline(user_id: uuid.UUID, message_text: str, session_id: uuid.UUID = None, history: list[dict] = None, mode_override: str = None) -> dict:
    memories = await retrieve_memories(user_id, message_text, limit=5)
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant memories."
    
    active_mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else "casual"
    system_prompt_to_use = get_system_prompt_for_mode(active_mode)
    contextualized_prompt = f"{system_prompt_to_use}\n\nContext Memories:\n{memory_context}"
    
    if history is None and session_id:
        history = await get_recent_session_messages(session_id, limit_turns=3)
        
    messages = list(history or []) + [{"role": "user", "content": message_text}]
    reply = await complete(contextualized_prompt, messages)
    
    intent = "small_talk"
    if reply.startswith("[") and "]" in reply[:30]:
        end_idx = reply.find("]")
        intent = reply[1:end_idx].lower()
        reply = reply[end_idx+1:].strip()
        
    final_mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else INTENT_TO_MODE.get(intent, "casual")

    exchange = f"User: {message_text}\nAssistant: {reply}"
    memory_eval = await complete(MEMORY_PROMPT, [{"role": "user", "content": exchange}])
    memory_eval = memory_eval.strip()
    
    if memory_eval != "NO" and memory_eval:
        await save_memory(user_id, memory_eval)
        
    return {"reply": reply, "intent": intent, "mode": final_mode}

async def extract_memory_from_exchange(user_id: uuid.UUID, message_text: str, reply: str):
    exchange = f"User: {message_text}\nAssistant: {reply}"
    memory_eval = await complete(MEMORY_PROMPT, [{"role": "user", "content": exchange}])
    memory_eval = memory_eval.strip()
    
    if memory_eval != "NO" and memory_eval:
        await save_memory(user_id, memory_eval)

from backend.services.llm_client import stream_complete
import re

import asyncio

USER_MEMORY_CACHE = {}

async def _stream_with_intent_parsed(gen, on_intent_parsed=None, mode_override: str = None):
    buffer = ""
    intent_parsed = False
    
    async for chunk in gen:
        if not intent_parsed:
            buffer += chunk
            if "]" in buffer:
                end_idx = buffer.find("]")
                intent = buffer[1:end_idx].lower()
                remaining = buffer[end_idx+1:].lstrip()
                intent_parsed = True
                if on_intent_parsed:
                    mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else INTENT_TO_MODE.get(intent, "casual")
                    try:
                        on_intent_parsed(intent, mode)
                    except TypeError:
                        on_intent_parsed(intent)
                if remaining:
                    yield remaining
            elif len(buffer) > 30 and "[" not in buffer:
                # Fallback if LLM forgot the tag
                intent = "small_talk"
                intent_parsed = True
                if on_intent_parsed:
                    mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else "casual"
                    try:
                        on_intent_parsed(intent, mode)
                    except TypeError:
                        on_intent_parsed(intent)
                yield buffer
        else:
            yield chunk

async def prefetch_memories(user_id: uuid.UUID, message_text: str):
    """Background task to fetch and cache memories based on the current conversational topic."""
    try:
        memories = await retrieve_memories(user_id, message_text, limit=5)
        if memories:
            USER_MEMORY_CACHE[user_id] = "\n".join([f"- {m}" for m in memories])
    except Exception as e:
        logger.error(f"Error prefetching memories: {e}")

async def run_pipeline_streaming(user_id: uuid.UUID, message_text: str, session_id: uuid.UUID = None, history: list[dict] = None, mode_override: str = None, on_intent_parsed=None):
    # Fetch from ultra-fast in-memory cache populated by previous turns
    memory_context = USER_MEMORY_CACHE.get(user_id, "No relevant memories yet.")
    
    # Fire off a background task to fetch memories for the NEXT turn based on THIS turn's topic
    # This completely removes the 6-second DB/Embed delay from the critical path!
    asyncio.create_task(prefetch_memories(user_id, message_text))
    
    active_mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else "casual"
    system_prompt_to_use = get_system_prompt_for_mode(active_mode)
    contextualized_prompt = f"{system_prompt_to_use}\n\nContext Memories:\n{memory_context}"
    
    if history is None and session_id:
        history = await get_recent_session_messages(session_id, limit_turns=3)
        
    messages = list(history or []) + [{"role": "user", "content": message_text}]
    gen = stream_complete(contextualized_prompt, messages)
    
    return "streaming", _stream_with_intent_parsed(gen, on_intent_parsed, mode_override)
