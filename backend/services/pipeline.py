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

SYSTEM_PROMPT = """You are a calm, comforting, and highly capable voice assistant. 
Be concise but warm. Use the user's context and memories below to inform your response, but do not mention the memories directly unless relevant.

CRITICAL: Your response MUST start exactly with an intent tag in brackets, chosen from: [small_talk], [question], [instruction], or [emotional]. Immediately after the tag, provide your response.
Example: [small_talk] It's so nice to hear from you!"""

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

async def _stream_with_intent_parsed(gen):
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
                if remaining:
                    yield remaining
            elif len(buffer) > 30 and "[" not in buffer:
                # Fallback if LLM forgot the tag
                intent = "small_talk"
                intent_parsed = True
                yield buffer
        else:
            yield chunk

async def run_pipeline_streaming(user_id: uuid.UUID, message_text: str):
    # To prevent 5-7s latency spikes on Render/Neon free tiers (due to slow CPU fastembed 
    # and cold-start DB queries), we bypass synchronous memory retrieval for voice.
    # Memories are still extracted in the background via run_pipeline for text chat.
    memory_context = "No relevant memories for this rapid voice turn."
    contextualized_prompt = f"{SYSTEM_PROMPT}\n\nContext Memories:\n{memory_context}"
    
    gen = stream_complete(contextualized_prompt, [{"role": "user", "content": message_text}])
    
    # We can't return intent synchronously anymore because it streams.
    # The caller expects (intent, text_gen). We'll default intent here to "streaming" and caller can just ignore it for voice.
    return "streaming", _stream_with_intent_parsed(gen)
