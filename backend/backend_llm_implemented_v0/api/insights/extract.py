# api/insights/extract.py
import re
from datetime import datetime
from typing import Dict, Any, List

LOWER = lambda s: s.lower()

def _minute_bucket(n: int) -> str:
    if n <= 20: return "micro_10_20"
    if n <= 50: return "standard_25_45"
    if n <= 110: return "deep_60_90"
    return "marathon_ge_120"

def _deadline_from_text(t: str) -> str | None:
    t = t.lower()
    # week(s)
    m = re.search(r"\b(in|within)\s*(\d+)\s*week", t)
    if m:
        w = int(m.group(2))
        return "immediate_lt_1w" if w < 1 else ("near_term_1_4w" if w <= 4 else "mid_term_1_3m")
    if re.search(r"\bthis week|next week|by (friday|monday|tuesday|wednesday|thursday)\b", t): return "immediate_lt_1w"
    if re.search(r"\b(2|3|4)\s*weeks\b", t): return "near_term_1_4w"
    if re.search(r"\b(1|2|3)\s*month", t): return "mid_term_1_3m"
    if re.search(r"\b(quarter|q\d|several months|> ?3 months|over the next few months)\b", t): return "long_term_gt_3m"
    if re.search(r"\bno deadline|no rush|whenever\b", t): return "none"
    return None

def _modality_hits(t: str) -> List[str]:
    t = t.lower()
    picks = set()
    if re.search(r"\b(video|youtube|watch|screencast|diagram|visual)\b", t): picks.add("visual")
    if re.search(r"\b(read|article|docs?|text)\b", t): picks.add("text_first")
    if re.search(r"\b(audio|podcast|listen)\b", t): picks.add("audio")
    if re.search(r"\b(hands[- ]?on|build|project|exercise|practice)\b", t): picks.add("hands_on")
    return list(picks)

def _availability_hits(t: str) -> List[str]:
    t = t.lower()
    picks = set()
    if "morning" in t: picks.add("morning")
    if "midday" in t or "lunch" in t: picks.add("midday")
    if "evening" in t or "after work" in t or "night" in t: picks.add("evening")
    if re.search(r"\b(late night|midnight|night shift)\b", t): picks.add("night")
    return list(picks)

def _interactivity(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(project[- ]?first|build a|ship|demo)\b", t): return "project_first"
    if re.search(r"\b(exercise[- ]?first|practice problems?|quizzes?)\b", t): return "exercise_first"
    if re.search(r"\b(lecture|read|watch)\b", t): return "passive_first"
    return None

def _tradeoff(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(asap|as fast as possible|quick|deadline|time[- ]?boxed)\b", t): return "time"
    if re.search(r"\b(high quality|quality|best practice|polish)\b", t): return "quality"
    if re.search(r"\b(scope|mvp|minimal viable)\b", t): return "scope"
    if re.search(r"\b(budget|cheap|low cost|cost)\b", t): return "cost"
    if "risk" in t: return "risk"
    return None

def _goal_type(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(ship|deliverable|demo|publish|launch)\b", t): return "deliverable_shipped"
    if re.search(r"\b(target|score|metric|kpi|accuracy|throughput)\b", t): return "performance_target"
    if re.search(r"\b(learn|proficien[ct]|become proficient|master)\b", t): return "proficiency_level"
    if re.search(r"\b(habit|routine|change.*behavio?r)\b", t): return "behavior_change"
    if re.search(r"\b(stakeholder|sign[- ]?off|approval)\b", t): return "stakeholder_signoff"
    return None

def _chunk_size(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(bite[- ]?sized|tiny|micro)\b", t): return "micro"
    if re.search(r"\b(small steps?|not too big|manageable)\b", t): return "small"
    if "medium" in t: return "medium"
    if re.search(r"\b(large tasks?|big chunks?)\b", t): return "large"
    return None

def _ramp_rate(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(start slow|gradual|ease in)\b", t): return "conservative"
    if re.search(r"\b(aggressive|ramp fast)\b", t): return "aggressive"
    return None  # default later -> balanced

def _parallelism(t: str) -> str | None:
    t = t.lower()
    if re.search(r"\b(one thing at a time|single[- ]?thread)\b", t): return "single"
    if re.search(r"\b(in parallel|multi[- ]?task|multiple at once)\b", t): return "multi"
    return None

def _checkpoint(t: str) -> str | None:
    t = t.lower()
    if "daily" in t: return "daily"
    if "weekly" in t: return "weekly"
    if re.search(r"\bcontinuous|kanban\b", t): return "continuous"
    if "milestone" in t: return "milestone_only"
    return None

def extract_insights(prompt: str) -> Dict[str, Dict[str, Any]]:
    """
    Returns a dict: field -> EnumField-like dict {value, confidence, source, evidence}
    Multi-value fields return list[str] in 'value'.
    """
    text = prompt.strip()
    if not text:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    ev = lambda span: [span][:1]  # keep a tiny evidence snippet

    # deadline
    dl = _deadline_from_text(text)
    if dl: out["deadline_profile"] = {"value": dl, "confidence": 0.9, "source": "auto_extract", "evidence": ev(dl)}

    # modality (multi)
    mods = _modality_hits(text)
    if mods: out["modality"] = {"value": sorted(set(mods)), "confidence": 0.9, "source": "auto_extract", "evidence": ev(", ".join(mods))}

    # availability (multi)
    av = _availability_hits(text)
    if av: out["availability_windows"] = {"value": sorted(set(av)), "confidence": 0.9, "source": "auto_extract", "evidence": ev(", ".join(av))}

    # session length (minutes)
    m = re.search(r"\b(\d{2,3})\s*(mins?|minutes?)\b", text.lower())
    if m:
        bucket = _minute_bucket(int(m.group(1)))
        out["session_length"] = {"value": bucket, "confidence": 0.95, "source": "auto_extract", "evidence": ev(m.group(0))}

    # interactivity
    inter = _interactivity(text)
    if inter: out["interactivity_level"] = {"value": inter, "confidence": 0.9, "source": "auto_extract", "evidence": ev(inter)}

    # trade-offs
    tr = _tradeoff(text)
    if tr: out["tradeoff_priority"] = {"value": tr, "confidence": 0.85, "source": "auto_extract", "evidence": ev(tr)}

    # goal
    gt = _goal_type(text)
    if gt: out["goal_type"] = {"value": gt, "confidence": 0.8, "source": "auto_extract", "evidence": ev(gt)}

    # chunk size / ramp / parallel / checkpoints
    cs = _chunk_size(text)
    if cs: out["chunk_size"] = {"value": cs, "confidence": 0.8, "source": "auto_extract", "evidence": ev(cs)}
    rr = _ramp_rate(text) or "balanced" if "balanced" in text.lower() else None
    if rr: out["ramp_rate"] = {"value": rr, "confidence": 0.7 if rr == "balanced" else 0.85, "source": "auto_extract", "evidence": ev(rr)}
    par = _parallelism(text)
    if par: out["parallelism"] = {"value": par, "confidence": 0.85, "source": "auto_extract", "evidence": ev(par)}
    chk = _checkpoint(text)
    if chk: out["checkpoint_frequency"] = {"value": chk, "confidence": 0.85, "source": "auto_extract", "evidence": ev(chk)}

    # normalize timestamps
    now = datetime.utcnow()
    for v in out.values():
        v["updated_at"] = now
    return out
