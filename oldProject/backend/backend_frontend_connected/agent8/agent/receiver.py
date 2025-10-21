
import re, json
from datetime import datetime, timedelta
from agent.nlp.detect import detect_intent, detect_affect

def _sanitize_prompt(text: str) -> str:
    t = text.replace("\r", " ").replace("\n", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t

def _truncate_200w(summary: str) -> str:
    words = summary.split()
    if len(words) <= 200:
        return summary
    truncated = " ".join(words[:200])
    idx = truncated.rfind(".")
    return truncated if idx < 100 else truncated[:idx+1]

def _choose_candidate_problem(thread_state, policy):
    recent_cutoff = datetime.utcnow() - timedelta(days=30)
    best_score, best = -1, None
    for pr in thread_state.get("problem_records", []):
        lu = pr.get("last_updated", "")
        try:
            lu_dt = datetime.strptime(lu.replace("Z",""), "%Y-%m-%dT%H:%M:%S.%f")
        except Exception:
            lu_dt = recent_cutoff
        is_recent = lu_dt >= recent_cutoff
        has_progress = (pr.get("turns",0) >= policy.get("progress_threshold",{}).get("min_turns",1)) and bool(pr.get("evidence_used", False))
        score = (2 if is_recent else 0) + (1 if has_progress else 0)
        if score > best_score:
            best_score, best = score, pr
    return best if best_score > 0 else None

def receive_prompt(env, thread_state, raw_prompt: str):
    prompt_clean = _sanitize_prompt(raw_prompt)
    if not prompt_clean:
        return {"ok": False, "error": "EMPTY_PROMPT", "final_response_md": "I didn’t catch a question. Please type your request."}

    history_summary = _truncate_200w(thread_state.get("history_summary",""))
    session_profile = thread_state.get("session_profile", {})

    
    from agent.nlp.detect import detect_intent, detect_affect
    intent = detect_intent(prompt_clean)
    affect = detect_affect(prompt_clean)
    candidate = _choose_candidate_problem(thread_state, env.get("thread_policy", {}))

    envelope = {
        "prompt_clean": prompt_clean,
        "history_summary": history_summary,
        "intent": intent,
        "affect": affect,
        "candidate_problem_record": candidate if candidate else None,
        "session_profile": session_profile
    }
    return {"ok": True, "request_envelope": envelope}
