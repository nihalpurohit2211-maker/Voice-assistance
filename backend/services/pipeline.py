import uuid
import logging
from backend.services.memory_store import retrieve_memories, save_memory
from backend.services.llm_client import complete

logger = logging.getLogger(__name__)

INTENT_PROMPT = """Classify the user's intent. Output exactly one word from this list and nothing else:
small_talk
question
instruction
emotional"""

SYSTEM_PROMPT = """You are a calm, comforting, and reassuring voice assistant. Your presence is steady, kind, and patient. Speak with gentle warmth and understanding—never clinical, rushed, or overly cheerful. Listen deeply, acknowledge the user with care, and offer thoughtful, grounded answers. Keep responses naturally concise for spoken conversation. Use the user's context and memories below to inform your response, but do not mention the memories directly unless relevant.

CRITICAL: Your response MUST start exactly with an intent tag in brackets, chosen from: [small_talk], [question], [instruction], or [emotional]. Immediately after the tag, provide your response.
Example: [small_talk] Take your time. I'm right here with you."""

MEMORY_PROMPT = """Analyze the following exchange. Does it contain a persistent, factual piece of information about the user that is worth remembering long-term?
If yes, output a concise single sentence summarizing the fact.
If no, output exactly 'NO'."""

async def run_pipeline(user_id: uuid.UUID, message_text: str) -> dict:
    memories = await retrieve_memories(user_id, message_text, limit=5)
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant memories."
    
    contextualized_prompt = f"{SYSTEM_PROMPT}\n\nContext Memories:\n{memory_context}"
    reply = await complete(contextualized_prompt, [{"role": "user", "content": message_text}])
    
    intent = "small_talk"
    if reply.startswith("[") and "]" in reply[:30]:
        end_idx = reply.find("]")
        intent = reply[1:end_idx].lower()
        reply = reply[end_idx+1:].strip()
        
    exchange = f"User: {message_text}\nAssistant: {reply}"
    memory_eval = await complete(MEMORY_PROMPT, [{"role": "user", "content": exchange}])
    memory_eval = memory_eval.strip()
    
    if memory_eval != "NO" and memory_eval:
        await save_memory(user_id, memory_eval)
        
    return {"reply": reply, "intent": intent}

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

async def _stream_with_intent_parsed(gen, on_intent_parsed=None):
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
                    on_intent_parsed(intent)
                if remaining:
                    yield remaining
            elif len(buffer) > 30 and "[" not in buffer:
                # Fallback if LLM forgot the tag
                intent = "small_talk"
                intent_parsed = True
                if on_intent_parsed:
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

async def run_pipeline_streaming(user_id: uuid.UUID, message_text: str, on_intent_parsed=None):
    # Fetch from ultra-fast in-memory cache populated by previous turns
    memory_context = USER_MEMORY_CACHE.get(user_id, "No relevant memories yet.")
    
    # Fire off a background task to fetch memories for the NEXT turn based on THIS turn's topic
    # This completely removes the 6-second DB/Embed delay from the critical path!
    asyncio.create_task(prefetch_memories(user_id, message_text))
    
    contextualized_prompt = f"{SYSTEM_PROMPT}\n\nContext Memories:\n{memory_context}"
    
    gen = stream_complete(contextualized_prompt, [{"role": "user", "content": message_text}])
    
    return "streaming", _stream_with_intent_parsed(gen, on_intent_parsed)
