import httpx
import logging
import json
from backend.core.config import settings

logger = logging.getLogger(__name__)

async def complete(system_prompt: str, messages: list[dict], model: str = "openai/gpt-oss-20b") -> str:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = [{"role": "system", "content": system_prompt}] + messages
    
    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": 0.3,
    }
    
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Groq API error response: {e.response.text}")
            try:
                err_data = e.response.json().get("error", {})
                if err_data.get("code") == "tool_use_failed" and "failed_generation" in err_data:
                    fg = err_data["failed_generation"]
                    try:
                        fg_json = json.loads(fg)
                        args = fg_json.get("arguments")
                        if isinstance(args, dict):
                            resp = args.get("response") or args.get("content") or args.get("reply")
                            intent = args.get("intent", "small_talk")
                            if resp:
                                return f"[{intent}] {resp}"
                            return str(args)
                        elif args:
                            return str(args)
                    except Exception:
                        pass
                    import re
                    m = re.search(r'"arguments"\s*:\s*(.*)', fg, re.DOTALL)
                    if m:
                        content = m.group(1).rstrip('}').strip().strip('"')
                        return content
            except Exception:
                pass
            if attempt == 1:
                raise
            else:
                logger.warning(f"Groq API call failed, retrying: {e}")
        except httpx.HTTPError as e:
            if attempt == 1:
                logger.error(f"Groq API call failed after 2 attempts: {e}")
                raise
            else:
                logger.warning(f"Groq API call failed, retrying: {e}")

async def stream_complete(system_prompt: str, messages: list[dict], model: str = "openai/gpt-oss-20b"):
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = [{"role": "system", "content": system_prompt}] + messages
    
    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": 0.3,
        "stream": True
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data_json = json.loads(data_str)
                        if data_json.get("choices") and data_json["choices"][0].get("delta", {}).get("content"):
                            yield data_json["choices"][0]["delta"]["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
