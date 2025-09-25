
import os, json, subprocess, shlex, time
from datetime import datetime
from typing import Dict, Any, List

def _now_iso(): return datetime.utcnow().isoformat()+"Z"

def _role_title(role_catalog: Dict[str,Any], role_id: str) -> str:
    for r in (role_catalog or {}).get("roles", []):
        if r.get("id") == role_id:
            return r.get("title") or role_id
    return role_id or ""

def _role_terms(role_catalog: Dict[str,Any], role_id: str) -> List[str]:
    for r in (role_catalog or {}).get("roles", []):
        if r.get("id") == role_id:
            return list(dict.fromkeys((r.get("synonyms") or []) + [r.get("title", role_id)]))[:6]
    return [role_id] if role_id else []

def _painpoint_anchors(gpp: Dict[str,Any], pp_ids: List[str]) -> List[str]:
    out = []
    by_id = {p["id"]: p for p in (gpp or {}).get("pain_points", [])}
    for pid in (pp_ids or []):
        pp = by_id.get(pid)
        if not pp: continue
        out.extend(pp.get("anchors", []) or [])
    # keep short and avoid heavy unicode dashes causing tokenization issues by duplicating with hyphens
    norm = []
    for a in out:
        if not a: continue
        norm.append(a)
        norm.append(a.replace("–","-").replace("—","-"))
    return list(dict.fromkeys(norm))[:6]

def _painpoint_terms(gpp: Dict[str,Any], pp_ids: List[str]) -> List[str]:
    terms = []
    by_id = {p["id"]: p for p in (gpp or {}).get("pain_points", [])}
    for pid in (pp_ids or []):
        pp = by_id.get(pid); 
        if not pp: continue
        terms.extend(pp.get("synonyms", []))
        terms.extend(pp.get("signals", []))
    return list(dict.fromkeys(terms))[:8]  # dedupe + cap

def build_query(env: Dict[str,Any], step1: Dict[str,Any], step2: Dict[str,Any], step5: Dict[str,Any]) -> str:
    prompt = (step1.get("request_envelope",{}) or {}).get("prompt_clean","")
    role_id = (step2.get("problem_context",{}) or {}).get("employment_category")
    pp_ids = (step2.get("problem_context",{}) or {}).get("pain_points", [])
    catalogs = env.get("catalog_data",{})
    role_title = _role_title(catalogs.get("role_catalog",{}), role_id)
    role_terms = _role_terms(catalogs.get("role_catalog",{}), role_id)
    pp_terms = _painpoint_terms(catalogs.get("gpp_taxonomy",{}), pp_ids)
    pp_anchors = _painpoint_anchors(catalogs.get("gpp_taxonomy",{}), pp_ids)
    extras = " ".join((role_terms + pp_terms)[:10])
    anchors = " ".join(pp_anchors[:4])
    q = f"{prompt} | role:{role_title} | pain_points:{','.join(pp_ids)} | terms:{extras} | anchors:{anchors}"
    return q.strip()

def _cmd_for(cfg: Dict[str,Any], query: str, k: int, threshold: str) -> List[str]:
    py = cfg.get("python_exe","python")
    entry = cfg.get("entrypoint","rag_step5_retrieve.py")
    proj = cfg.get("rag_project_path","./rag")
    cmd = [py, entry, "retrieve", "--project", proj, "--q", query, "--k", str(k), "--threshold", threshold]
    return cmd

def _run_cli(cmd: List[str], cwd: str, timeout_sec: int) -> Dict[str,Any]:
    try:
        env = {**os.environ, "PYTHONUTF8":"1", "PYTHONIOENCODING":"utf-8"}
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=timeout_sec)
        stdout = proc.stdout.strip()
        if not stdout:
            return {"ok": False, "error": "NO_STDOUT", "stderr": proc.stderr}
        # The retriever prints a JSON dict with 'evidence_pack'
        data = json.loads(stdout)
        return {"ok": True, "data": data, "stderr": proc.stderr}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TIMEOUT", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": f"EXC:{e}"}

def _active_problem(thread_state: Dict[str,Any]) -> Dict[str,Any] | None:
    prs = thread_state.get("problem_records", [])
    if not prs: return None
    prs_sorted = sorted(prs, key=lambda p: p.get("last_updated",""), reverse=True)
    return prs_sorted[0]

def persist_evidence(thread_state: Dict[str,Any], problem_id: str, evidence_pack: List[Dict[str,Any]]):
    if not problem_id: return
    for pr in thread_state.get("problem_records", []):
        if pr.get("problem_id") == problem_id:
            pr["evidence_used"] = bool(evidence_pack)
            pr.setdefault("evidence_history", [])
            pr.setdefault("last_evidence_pack", [])
            pr["last_evidence_pack"] = evidence_pack
            pr["evidence_history"].append({"at": _now_iso(), "items": evidence_pack[:]})
            # cap history to last 5
            pr["evidence_history"] = pr["evidence_history"][-5:]
            pr["last_updated"] = _now_iso()
            return

def retrieve_and_attach(env: Dict[str,Any], thread_state: Dict[str,Any], step1: Dict[str,Any], step2: Dict[str,Any], step5: Dict[str,Any]) -> Dict[str,Any]:
    cfg = env.get("retriever_config") or {}
    rag_root = cfg.get("rag_project_path")
    if not rag_root or not os.path.exists(rag_root):
        return {"ok": True, "evidence_count": 0, "threshold": cfg.get("default_threshold","strict"),
                "note": "RAG root not configured or missing; running in decline mode."}

    k = int((step5.get("pcc",{}) or {}).get("retrieval",{}).get("top_k", cfg.get("default_k", 8)))
    threshold = cfg.get("default_threshold","strict")
    q = build_query(env, step1, step2, step5)
    cmd = _cmd_for(cfg, q, k, threshold)

    res = _run_cli(cmd, cwd=rag_root, timeout_sec=int(cfg.get("timeout_sec", 40)))
    if not res.get("ok"):
        return {"ok": True, "evidence_count": 0, "threshold": threshold, "error": res.get("error","run_failed"), "stderr": res.get("stderr","")}

    payload = res["data"]
    # The retriever prints {"evidence_pack":[...], "meta": {...}} (based on your design)
    pack = payload.get("evidence_pack") or payload.get("results") or []
    # Fallback if nothing above threshold → try lenient + larger k
    if not pack:
        k2 = max(k+6, int(cfg.get("default_k",8))+6)
        cmd2 = _cmd_for(cfg, q, k2, "lenient")
        res2 = _run_cli(cmd2, cwd=rag_root, timeout_sec=int(cfg.get("timeout_sec", 40)))
        if res2.get("ok"):
            payload2 = res2["data"]
            pack = payload2.get("evidence_pack") or payload2.get("results") or []
            threshold = "lenient"  # mark lowered threshold
            if not pack:
                # last attempt: reduce user prompt noise, focus on role+pp terms only
                base_q = f"role:{role_title} | pain_points:{','.join(pp_ids)} | terms:{' '.join((role_terms+pp_terms)[:10])} | anchors:{' '.join(pp_anchors[:4])}"
                cmd3 = _cmd_for(cfg, base_q, k2, "lenient")
                res3 = _run_cli(cmd3, cwd=rag_root, timeout_sec=int(cfg.get("timeout_sec", 40)))
                if res3.get("ok"):
                    payload3 = res3["data"]
                    pack = payload3.get("evidence_pack") or payload3.get("results") or []
    # Normalize each item to a small shape we carry forward
    norm = []
    for it in pack:
        norm.append({
            "anchor_id": it.get("anchor_id"),
            "score": it.get("score"),
            "snippet": it.get("snippet") or it.get("text","")[:240],
            "source_doc": it.get("source_doc") or it.get("meta",{}).get("source_doc"),
            "page": it.get("page") or it.get("meta",{}).get("page")
        })

    # Persist onto active problem
    pr = _active_problem(thread_state)
    problem_id = pr.get("problem_id") if pr else None
    persist_evidence(thread_state, problem_id, norm)

    return {"ok": True, "evidence_count": len(norm), "threshold": threshold, "query": q, "results": norm}
