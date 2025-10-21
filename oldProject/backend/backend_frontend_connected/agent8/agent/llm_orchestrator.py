
import os, json
from typing import Dict, Any, List, Optional

def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v if v and v.strip() else None

def _has_pkg(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False

def call_openai(model: str, messages: List[Dict[str,str]], timeout_sec: int) -> Dict[str,Any]:
    api_key = _env("OPENAI_API_KEY") or _env("OPENAI_APIKEY")
    if not api_key:
        return {"ok": False, "error": "NO_API_KEY"}
    try:
        if _has_pkg("openai"):
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            rsp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                timeout=timeout_sec,
            )
            text = rsp.choices[0].message.content or ""
            return {"ok": True, "content": text, "raw": {"usage": getattr(rsp, "usage", None)}}
        else:
            import requests
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": messages, "temperature": 0.2}
            r = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP_{r.status_code}", "body": r.text[:400]}
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            return {"ok": True, "content": text, "raw": {"usage": data.get("usage")}}
    except Exception as e:
        return {"ok": False, "error": f"EXC:{e.__class__.__name__}:{e}"}

def call_gemini(model: str, prompt_text: str, timeout_sec: int) -> Dict[str,Any]:
    api_key = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    if not api_key:
        return {"ok": False, "error": "NO_API_KEY"}
    try:
        if _has_pkg("google.generativeai"):
            import google.generativeai as genai
            genai.configure(api_key=api_key, transport="rest")
            model_obj = genai.GenerativeModel(model_name=model)
            rsp = model_obj.generate_content(prompt_text, request_options={"timeout": timeout_sec})
            text = getattr(rsp, "text", None) or (rsp.candidates[0].content.parts[0].text if rsp.candidates else "")
            return {"ok": True, "content": text, "raw": None}
        else:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            body = {"contents": [{"parts": [{"text": prompt_text}]}]}
            r = requests.post(url, headers=headers, json=body, timeout=timeout_sec)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP_{r.status_code}", "body": r.text[:400]}
            data = r.json()
            parts = data.get("candidates",[{}])[0].get("content",{}).get("parts",[])
            text = ""
            for p in parts:
                if "text" in p: text += p["text"]
            return {"ok": True, "content": text, "raw": None}
    except Exception as e:
        return {"ok": False, "error": f"EXC:{e.__class__.__name__}:{e}"}

def generate_with_fallback(llm_cfg: Dict[str,Any],
                           system_prompt: str,
                           user_prompt: str) -> Dict[str,Any]:
    policy = llm_cfg.get("policy", {})
    primary = llm_cfg.get("primary", {})
    fallback = llm_cfg.get("fallback", {})
    retries = int(policy.get("max_retries", 1))

    messages = [{"role":"system","content":system_prompt},
                {"role":"user","content":user_prompt}]

    # Primary
    for attempt in range(retries+1):
        if primary.get("name") == "openai":
            res = call_openai(primary.get("model","gpt-4o-mini"), messages, int(primary.get("timeout_sec",35)))
        else:
            res = {"ok": False, "error": "UNSUPPORTED_PRIMARY"}
        if res.get("ok"):
            return {"ok": True, "provider": "openai", "content": res["content"], "raw": res.get("raw")}
        last_err = res.get("error","unknown")

    # Fallback
    if fallback.get("name") == "gemini":
        prompt_text = f"System:\\n{system_prompt}\\n\\nUser:\\n{user_prompt}"
        res = call_gemini(fallback.get("model","gemini-2.0-flash"), prompt_text, int(fallback.get("timeout_sec",35)))
        if res.get("ok"):
            return {"ok": True, "provider": "gemini", "content": res["content"], "raw": res.get("raw")}
        last_err = res.get("error","unknown")

    # Dry-run if both unavailable
    if policy.get("dry_run_if_unavailable", True):
        content = (
            "Preface\\n"
            "We couldn't reach a model right now. Returning a rule-based draft using in-vault evidence.\\n\\n"
            "Core Summary\\n"
            "{CORE_SUMMARY}\\n\\n"
            "Evidence\\n"
            "{EVIDENCE}\\n\\n"
            "Checklist\\n"
            "{CHECKLIST}\\n\\n"
            "Closer\\n"
            "Reply with any missing info so we can refine.\\n\\n"
            "Sources\\n"
            "{SOURCES}"
        )
        return {"ok": True, "provider": "dry_run", "content": content, "raw": {"error": last_err}}

    return {"ok": False, "error": last_err or "GEN_FAILURE"}
