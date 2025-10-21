import os, inspect

def _get_problem_id(thread_state):
    try:
        prs = (thread_state.get("problem_records") or [])
        if prs:
            pr = prs[-1]
            return pr.get("problem_id", "unknown")
    except Exception:
        pass
    return "unknown"

def mirror_log_asked(thread_state, questions_obj):
    try:
        from .service import MemoryService
        ms = MemoryService()
        if not ms.enabled: return
        pid = _get_problem_id(thread_state) if isinstance(thread_state, dict) else "unknown"
        ms.log_asked(pid, "<batch>", questions_obj)
    except Exception:
        pass

def mirror_log_answered(thread_state, answers_obj):
    try:
        from .service import MemoryService
        ms = MemoryService()
        if not ms.enabled: return
        pid = _get_problem_id(thread_state) if isinstance(thread_state, dict) else "unknown"
        ms.log_answered(pid, "<batch>", answers_obj)
        if isinstance(answers_obj, dict):
            for k, v in answers_obj.items():
                if isinstance(k, str) and "." in k:
                    ms.save_insight(problem_id=pid, field_id=k, value=v, source="user", confidence=1.0, label=k)
    except Exception:
        pass

def mirror_save_inferred(thread_state, inferred_map):
    try:
        from .service import MemoryService
        ms = MemoryService()
        if not ms.enabled: return
        pid = _get_problem_id(thread_state) if isinstance(thread_state, dict) else "unknown"
        if isinstance(inferred_map, dict):
            for k, v in inferred_map.items():
                if isinstance(v, dict):
                    val = v.get("value", v)
                    conf = float(v.get("confidence", 0.7))
                else:
                    val = v; conf = 0.7
                ms.save_insight(problem_id=pid, field_id=k, value=val, source="nlp" if conf < 0.85 else "nlp_llm",
                                confidence=conf, label=k)
    except Exception:
        pass
