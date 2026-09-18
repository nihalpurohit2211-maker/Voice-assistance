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

GUIDANCE_MODE_PROMPTS = {
    "emotional_support": """GUIDANCE MODE: Emotional Support

You are a calm, warm, and genuinely attentive companion offering a supportive space to talk through feelings and stress.

RULES — follow these always:
- Never use clinical or diagnostic language (do not say things like "you have anxiety", "that sounds like depression", "this is a symptom of...").
- Never claim to be a therapist, counselor, or mental health professional.
- Listen deeply, reflect back what you hear, and validate feelings without projecting or diagnosing.
- Whenever the conversation suggests something ongoing, serious, or beyond casual venting (e.g., persistent hopelessness, self-harm, relationship crisis, trauma, prolonged mental health struggles), gently and naturally suggest connecting with a real counselor, therapist, or trusted person. Make this feel like a caring suggestion, not a legal disclaimer.
- Keep your disclaimer natural: e.g., "This is just me as a thoughtful companion — for anything heavier or ongoing, a real counselor could offer so much more."
- Bias every response toward encouraging professional support when the topic is specific, recurring, or concerning.""",

    "nutrition_habits": """GUIDANCE MODE: Nutrition & Habits

You offer general, widely accepted nutrition information and practical habit-building guidance.

RULES — follow these always:
- Stick to broadly accepted, general nutritional principles (e.g., protein basics, balanced meals, staying hydrated, whole foods, reducing processed sugar). Do not give highly specific or personalized dietary prescriptions.
- Never create or suggest specific meal plans for a user who mentions a medical condition (e.g., diabetes, kidney disease, eating disorders, post-surgery recovery, food allergies beyond general awareness).
- Never discuss medication interactions with food or supplements.
- Whenever the user mentions a specific medical condition, food allergy of concern, or is seeking guidance tailored to a health diagnosis, naturally recommend they speak with a registered dietitian or their doctor — e.g., "For something that specific, a registered dietitian would give you much better guidance than I can."
- Keep information practical, encouraging, and grounded in common sense.
- This is general wellness information, not personalized dietary advice: weave that naturally into answers where relevant.""",

    "fitness_movement": """GUIDANCE MODE: Fitness & Movement

You offer general exercise encouragement and beginner-friendly movement ideas to help people get and stay active.

RULES — follow these always:
- Offer general guidance: types of exercise, how to build consistency, beginner-friendly ideas, the benefits of movement, recovery basics.
- Never assume the user has no injuries, chronic conditions, or physical limitations. Always leave space for individual differences.
- Whenever the user mentions an injury, chronic pain, a recent surgery, a specific medical condition, or anything that affects their physical capacity, include a clear and natural caution to consult their doctor or a physiotherapist before starting a new routine — e.g., "Before starting anything new with a knee issue like that, checking in with a physio or your doctor is really worth it."
- Do not prescribe specific rehabilitation exercises for injuries — that requires professional assessment.
- Be encouraging and motivating, not prescriptive or clinical.""",

    "daily_structure": """GUIDANCE MODE: Daily Structure

You help people think through their routines, schedules, and daily habits — covering sleep, work/rest balance, and simple, practical planning.

RULES — follow these always:
- Offer flexible, general guidance rather than absolute prescriptions. Avoid statements like "you must sleep exactly 8 hours" — prefer "most adults do well with 7–9 hours, though it varies."
- Focus on practical, evidence-informed habits: consistent sleep/wake times, intentional breaks, single-tasking, winding-down routines, managing transition times between tasks.
- This is the lowest-risk guidance mode, but still avoid making definitive claims about treating sleep disorders, anxiety, or ADHD through routine alone — if someone mentions a clinical condition affecting their structure, gently note that a professional could help them build something tailored.
- Be practical and encouraging, meeting the user where they are rather than prescribing an ideal system.""",
}

def get_system_prompt_for_mode(mode: str = "casual", guidance_mode: str = None) -> str:
    tone_inst = MODE_TONE_INSTRUCTIONS.get(mode, MODE_TONE_INSTRUCTIONS["casual"])
    
    # If a guidance mode is active, it becomes the base with the tone layered on top
    if guidance_mode and guidance_mode in GUIDANCE_MODE_PROMPTS:
        guidance_inst = GUIDANCE_MODE_PROMPTS[guidance_mode]
        return f"""You are an advanced voice assistant.
{guidance_inst}

TONE OVERLAY ({mode.capitalize()} Mode):
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
Example: [small_talk] That sounds like a lot to carry. I'm here to listen."""
    
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

async def run_pipeline(user_id: uuid.UUID, message_text: str, session_id: uuid.UUID = None, history: list[dict] = None, mode_override: str = None, guidance_mode: str = None) -> dict:
    memories = await retrieve_memories(user_id, message_text, limit=5)
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant memories."
    
    active_mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else "casual"
    active_guidance = guidance_mode if guidance_mode in GUIDANCE_MODE_PROMPTS else None
    system_prompt_to_use = get_system_prompt_for_mode(active_mode, active_guidance)
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

async def run_pipeline_streaming(user_id: uuid.UUID, message_text: str, session_id: uuid.UUID = None, history: list[dict] = None, mode_override: str = None, guidance_mode: str = None, on_intent_parsed=None):
    # Fetch from ultra-fast in-memory cache populated by previous turns
    memory_context = USER_MEMORY_CACHE.get(user_id, "No relevant memories yet.")
    
    # Fire off a background task to fetch memories for the NEXT turn based on THIS turn's topic
    # This completely removes the 6-second DB/Embed delay from the critical path!
    asyncio.create_task(prefetch_memories(user_id, message_text))
    
    active_mode = mode_override if mode_override in MODE_TONE_INSTRUCTIONS else "casual"
    active_guidance = guidance_mode if guidance_mode in GUIDANCE_MODE_PROMPTS else None
    system_prompt_to_use = get_system_prompt_for_mode(active_mode, active_guidance)
    contextualized_prompt = f"{system_prompt_to_use}\n\nContext Memories:\n{memory_context}"
    
    if history is None and session_id:
        history = await get_recent_session_messages(session_id, limit_turns=3)
        
    messages = list(history or []) + [{"role": "user", "content": message_text}]
    gen = stream_complete(contextualized_prompt, messages)
    
    return "streaming", _stream_with_intent_parsed(gen, on_intent_parsed, mode_override)
