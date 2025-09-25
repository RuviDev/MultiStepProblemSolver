import os
from typing import Optional, Tuple

def summarize(label: str, canonical_value, source: str, confidence: float
             ) -> Tuple[str, Optional[str], str, Optional[str]]:
    use_llm = os.getenv("MEMORY_SUMMARIZER_USE_LLM", "false").lower() == "true"
    if not use_llm:
        return f"**{label}** → {canonical_value}.", "Captured from " + source, "rule_based", None
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = (
            "Rewrite the following insight as a single, neutral, 1–2-line markdown bullet.\n"
            "Do NOT change the meaning or the value. Keep it succinct.\n\n"
            f"Label: {label}\nValue: {canonical_value}\nSource: {source}\nConfidence: {confidence}\n"
        )
        resp = client.chat.completions.create(
            model=os.getenv("MEMORY_SUMMARIZER_MODEL", "gpt-4o-mini"),
            messages=[{"role":"system","content":"You are a terse summarizer."},
                      {"role":"user","content":prompt}],
            temperature=0.2,
            max_tokens=120
        )
        text = resp.choices[0].message.content.strip()
        return text, "LLM phrasing of captured insight.", "openai", os.getenv("MEMORY_SUMMARIZER_MODEL", "gpt-4o-mini")
    except Exception:
        return f"**{label}** → {canonical_value}.", "Captured from " + source, "rule_based", None
