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
Be concise but warm. Use the user's context and memories below to inform your response, but do not mention the memories directly unless relevant."""

MEMORY_PROMPT = """Analyze the following exchange. Does it contain a persistent, factual piece of information about the user that is worth remembering long-term?
If yes, output a concise single sentence summarizing the fact.
If no, output exactly 'NO'."""

async def run_pipeline(user_id: uuid.UUID, message_text: str) -> dict:
    # 1 & 2. Retrieve memories
    memories = await retrieve_memories(user_id, message_text, limit=5)
    
    # 3. Classify intent
    raw_intent = await complete(INTENT_PROMPT, [{"role": "user", "content": message_text}])
    raw_intent = raw_intent.strip().lower()
    
    valid_intents = {"small_talk", "question", "instruction", "emotional"}
    if raw_intent in valid_intents:
        intent = raw_intent
    else:
        logger.warning(f"Unexpected intent parsed: '{raw_intent}'. Defaulting to small_talk.")
        intent = "small_talk"
        
    # 4 & 5. Final reply
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant memories."
    
    contextualized_prompt = f"{SYSTEM_PROMPT}\n\nContext Memories:\n{memory_context}\n\nDetected Intent: {intent}"
    reply = await complete(contextualized_prompt, [{"role": "user", "content": message_text}])
    
    # 6. Memory extraction
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

async def run_pipeline_streaming(user_id: uuid.UUID, message_text: str):
    memories = await retrieve_memories(user_id, message_text, limit=5)
    
    raw_intent = await complete(INTENT_PROMPT, [{"role": "user", "content": message_text}])
    raw_intent = raw_intent.strip().lower()
    
    valid_intents = {"small_talk", "question", "instruction", "emotional"}
    intent = raw_intent if raw_intent in valid_intents else "small_talk"
    
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant memories."
    contextualized_prompt = f"{SYSTEM_PROMPT}\n\nContext Memories:\n{memory_context}\n\nDetected Intent: {intent}"
    
    gen = stream_complete(contextualized_prompt, [{"role": "user", "content": message_text}])
    return intent, gen
