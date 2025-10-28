# app/core/llm.py
from __future__ import annotations
from typing import Optional

from openai import APIError, RateLimitError, APITimeoutError
from app.core.openai_client import client, DEFAULT_MODEL, REQUEST_TIMEOUT

# Return the raw model string (Component 10 will parse/validate)
async def complete_json(
    *,
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 120,
    system: Optional[str] = None,
) -> str:
    """
    Calls the chat completion API with JSON response mode enforced and returns the raw content.
    The caller is responsible for JSON parsing/validation.
    """
    sys = system or "You are a precise JSON generator. Output ONLY one JSON object, no markdown."
    try:
        # Bind timeout on the call
        _cl = client.with_options(timeout=REQUEST_TIMEOUT)

        resp = await _cl.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt},
            ],
            # Force JSON-mode (supported on modern models)
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content
    except (RateLimitError, APITimeoutError) as e:
        # Bubble up; Component 10 has its own fallback
        raise
    except APIError as e:
        raise
