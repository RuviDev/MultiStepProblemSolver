# agent8/agent/survey_io.py
# Backward-compatible survey utilities for UIA/UIA→UAA flow.
# - export_current_survey: accepts BOTH old (ts, pcc/step5) and new (env, ts, missing_fields) signatures
# - apply_survey_answers: merge user answers into active ProblemRecord.insights

from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime
from pathlib import Path
import json


# -------------------------
# Utilities
# -------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _active_problem(ts: Dict[str, Any]) -> Dict[str, Any] | None:
    """Return the active ProblemRecord if present, else last record, else None."""
    prs = ts.get("problem_records", []) or []
    for p in prs:
        if p.get("is_active"):
            return p
    return prs[-1] if prs else None


def _ensure_problem(ts: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure there is at least one ProblemRecord to write answers into."""
    pr = _active_problem(ts)
    if pr:
        return pr
    pr = {
        "problem_id": f"adhoc-{int(datetime.utcnow().timestamp())}",
        "is_active": True,
        "insights": {},
        "asked_fields": [],
        "generation_history": [],
        "last_response": {},
    }
    ts.setdefault("problem_records", []).append(pr)
    return pr


def _project_config_dir() -> Path:
    """
    Best-effort resolver for agent8/config when env is not passed (legacy mode).
    survey_io.py lives at .../agent8/agent/survey_io.py
    """
    here = Path(__file__).resolve()
    cfg = here.parents[1] / "config"
    return cfg


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _catalog_meta_map_from_env_or_disk(env: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    """
    Build canonical field metadata: id -> {label, type, options}
    Prefer env['catalog_data']['git_insight_catalog']; fallback to config JSON on disk.
    """
    git_cat = {}
    if env and isinstance(env, dict):
        git_cat = ((env.get("catalog_data", {}) or {}).get("git_insight_catalog", {}) or {})
    if not git_cat:
        cfg = _project_config_dir()
        git_cat = _load_json(cfg / "insight_catalog_git.json")

    meta_map: Dict[str, Dict[str, Any]] = {}
    for node in git_cat.get("fields", []) or []:
        for ch in node.get("children", []) or []:
            cid = ch.get("id")
            if not cid:
                continue
            meta_map[cid] = {
                "label": ch.get("label", cid.split(".")[-1].replace("_", " ").title()),
                "type": ch.get("type", "text"),
                "options": ch.get("values", []),
            }
    return meta_map


def _policy_from_env_or_disk(env: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Prefer env['thread_policy']; fallback to config JSON on disk.
    """
    policy = {}
    if env and isinstance(env, dict):
        policy = env.get("thread_policy", {}) or {}
    if not policy:
        cfg = _project_config_dir()
        policy = _load_json(cfg / "thread_policy.json")
    return policy or {}


def _unpack_export_args(*args, **kwargs) -> Tuple[Dict[str, Any] | None, Dict[str, Any], List[str]]:
    """
    Support both signatures:
      1) export_current_survey(env, ts, missing_fields)
      2) export_current_survey(ts, pcc_or_step5)  # legacy

    Returns: (env_or_none, ts, missing_fields:list)
    """
    # New-style explicit signature
    if len(args) >= 3:
        env, ts, missing_fields = args[0], args[1], args[2]
        if not isinstance(missing_fields, list):
            missing_fields = list(missing_fields) if missing_fields else []
        return env, ts, missing_fields

    # Legacy two-arg form
    if len(args) == 2:
        ts, pcc_or_step5 = args[0], args[1]
        # Try to extract missing_fields from the object (supports step5 or its 'pcc')
        if isinstance(pcc_or_step5, dict):
            if "missing_fields" in pcc_or_step5:
                missing_fields = pcc_or_step5.get("missing_fields", []) or []
            elif "pcc" in pcc_or_step5 and isinstance(pcc_or_step5["pcc"], dict):
                missing_fields = pcc_or_step5["pcc"].get("missing_fields", []) or []
            else:
                missing_fields = []
        else:
            missing_fields = []
        return None, ts, missing_fields

    # Keyword-arg fallbacks
    env = kwargs.get("env")
    ts = kwargs.get("ts") or kwargs.get("thread_state") or {}
    missing_fields = kwargs.get("missing_fields", []) or []
    if not isinstance(missing_fields, list):
        missing_fields = list(missing_fields)
    return env, ts, missing_fields


# -------------------------
# Public API
# -------------------------

def export_current_survey(*args, **kwargs) -> Dict[str, Any]:
    """
    Build a *small* list of questions for canonical missing fields.

    Accepts:
      - export_current_survey(env, ts, missing_fields)
      - export_current_survey(ts, pcc_or_step5)         # legacy (env loaded from disk)

    Rules:
      - Limit to thread_policy.max_insight_questions_per_turn (default 2)
      - Skip fields already asked (ProblemRecord.asked_fields)
      - Pull label/options from the git catalog
      - Preserve input order of missing_fields, then slice

    Returns: {"questions":[{field_id, type, label, (options?)}]}
    """
    env, ts, missing_fields = _unpack_export_args(*args, **kwargs)

    policy = _policy_from_env_or_disk(env)
    max_q = int(policy.get("max_insight_questions_per_turn", 2))

    meta_map = _catalog_meta_map_from_env_or_disk(env)

    pr = _ensure_problem(ts)
    already = set(pr.get("asked_fields", []) or [])

    selected_ids = [fid for fid in (missing_fields or []) if fid not in already][:max_q]

    questions: List[Dict[str, Any]] = []
    for fid in selected_ids:
        meta = meta_map.get(fid, {})
        qtype = "select" if meta.get("type") == "enum" else "text"
        q = {
            "field_id": fid,
            "type": qtype,
            "label": meta.get("label", fid.split(".")[-1].replace("_", " ").title()),
        }
        if qtype == "select":
            q["options"] = list(meta.get("options", []) or [])
        questions.append(q)

    return {"questions": questions}


def apply_survey_answers(env: Dict[str, Any],
                         ts: Dict[str, Any],
                         answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge user-provided answers (canonical field_id -> value) into the active ProblemRecord.

    Behavior:
      - Write to ProblemRecord.insights[fid] with:
          { "value": value, "confidence": 0.95, "source": "user",
            "status": "answered", "provenance": {"mode": "survey"}, "updated_at": now }
      - Preserve previous value in 'history'
      - Add each fid to 'asked_fields' to avoid re-asking
      - Return summary
    """
    pr = _ensure_problem(ts)
    pr.setdefault("insights", {})
    pr.setdefault("asked_fields", [])

    merged = 0
    skipped = 0
    touched: List[str] = []

    if not isinstance(answers, dict):
        return {"ok": False, "error": "answers must be a dict of {field_id: value}"}

    for fid, value in answers.items():
        if not fid:
            skipped += 1
            continue

        new_rec = {
            "value": value,
            "confidence": 0.95,
            "source": "user",
            "status": "answered",
            "provenance": {"mode": "survey"},
            "updated_at": _now_iso(),
        }

        if fid in pr["insights"]:
            prev = pr["insights"][fid]
            hist = {
                "value": prev.get("value"),
                "confidence": prev.get("confidence", 0),
                "source": prev.get("source", "nlp"),
                "updated_at": prev.get("updated_at"),
            }
            prev.setdefault("history", []).append(hist)
            pr["insights"][fid].update(new_rec)
        else:
            pr["insights"][fid] = new_rec

        if fid not in pr["asked_fields"]:
            pr["asked_fields"].append(fid)

        merged += 1
        touched.append(fid)

    pr["last_updated"] = _now_iso()

    return {
        "ok": True,
        "merged": merged,
        "skipped": skipped,
        "asked_fields": list(pr.get("asked_fields", [])),
        "touched": touched,
    }
