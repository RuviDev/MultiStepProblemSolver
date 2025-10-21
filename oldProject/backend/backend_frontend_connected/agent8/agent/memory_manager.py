import os, json, time
from typing import Dict, Any

PROFILE_PATH = os.path.join("state", "profile.json")

def _now() -> int:
    try:
        return int(time.time())
    except Exception:
        return 0

def load_profile() -> Dict[str, Any]:
    if not os.path.exists(PROFILE_PATH):
        return {"user_prefs": {}, "stats": {}, "updated_at": _now()}
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"user_prefs": {}, "stats": {}, "updated_at": _now()}

def save_profile(p: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    p["updated_at"] = _now()
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def update_profile_from_turn(profile: Dict[str,Any],
                             thread_state: Dict[str,Any],
                             res1: Dict[str,Any],
                             effective_pcc: Dict[str,Any]) -> Dict[str,Any]:
    prefs = profile.setdefault("user_prefs", {})
    tone_override = (res1 or {}).get("request_envelope",{}).get("tone_override")
    if tone_override:
        prefs["tone_preference"] = {"value": tone_override, "ts": _now()}
    prs = (thread_state or {}).get("problem_records") or []
    if prs and prs[-1].get("no_more_questions") is True:
        prefs["micro_questions"] = {"value": "deny", "ts": _now()}
    lang = (effective_pcc or {}).get("language")
    if lang:
        prefs["language"] = {"value": lang, "ts": _now()}
    return profile
