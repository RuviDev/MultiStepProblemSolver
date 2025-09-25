
import json, os

REQUIRED = [
    "role_catalog.json",
    "painpoint_taxonomy_gpp.json",
    "insight_catalog_git.json",
    "pcc_defaults.json",
    "thread_policy.json",
    "vault_index.json"
]

def _checksum(obj) -> str:
    import hashlib
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:10]

def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _collect_git_ids(git):
    ids = set()
    for node in git.get("fields", []):
        ids.add(node["id"])
        for ch in node.get("children", []):
            ids.add(ch["id"])
    return ids

def _collect_vault_anchors(vault):
    anchors=set()
    for d in vault.get("docs", []):
        for a in d.get("anchors", []):
            anchors.add(a)
    return anchors

def _validate_gpp(gpp, git_ids, vault_anchors):
    inactive = {"requires_insights": [], "anchors": []}
    for p in gpp.get("pain_points", []):
        for rid in p.get("requires_insights", []):
            if rid not in git_ids:
                inactive["requires_insights"].append({"pain_point": p["id"], "missing_field": rid})
        for a in p.get("anchors", []):
            if a not in vault_anchors:
                inactive["anchors"].append({"pain_point": p["id"], "missing_anchor": a})
    return inactive

def build_environment_context(config_dir: str, thread_id: str = "T-APP-001"):
    artifacts = {name: _load(os.path.join(config_dir, name)) for name in REQUIRED}
    retriever_cfg = _try_load_optional(os.path.join(config_dir, "retriever.json"))
    llm_providers = _try_load_optional(os.path.join(config_dir, "llm_providers.json"))
    git_ids = _collect_git_ids(artifacts["insight_catalog_git.json"])
    vault_anchors = _collect_vault_anchors(artifacts["vault_index.json"])
    inactive_refs = _validate_gpp(artifacts["painpoint_taxonomy_gpp.json"], git_ids, vault_anchors)

    pcc = dict(artifacts["pcc_defaults.json"])
    pcc.setdefault("format","markdown"); pcc.setdefault("language","en")
    pcc.setdefault("permissions_tools",["evidence_vault"])
    pcc.setdefault("verification_controls",{"must_cite": True, "fallback_ok": True})
    pcc.setdefault("target_tokens", 450); pcc.setdefault("max_tokens", 900)
    pcc.setdefault("tone_escalation", ["neutral","motivational"])
    pcc.setdefault("layered_template", ["Preface","Core Summary","Evidence","Checklist","Closer","Sources"])

    versions = { k: artifacts[k].get("version","v?") for k in artifacts }
    sums = { k: _checksum(artifacts[k]) for k in artifacts }

    env = {
        "thread_id": thread_id,
        "catalogs": {
            "role_catalog": { "version": versions["role_catalog.json"], "checksum": sums["role_catalog.json"] },
            "gpp_taxonomy": { "version": versions["painpoint_taxonomy_gpp.json"], "checksum": sums["painpoint_taxonomy_gpp.json"] },
            "git_insight_catalog": { "version": versions["insight_catalog_git.json"], "checksum": sums["insight_catalog_git.json"] },
            "vault_index": { "version": versions["vault_index.json"], "checksum": sums["vault_index.json"] }
        },
        "catalog_data": {
            "role_catalog": artifacts["role_catalog.json"],
            "gpp_taxonomy": artifacts["painpoint_taxonomy_gpp.json"],
            "git_insight_catalog": artifacts["insight_catalog_git.json"]
        },
        "pcc_defaults": pcc,
        "thread_policy": artifacts["thread_policy.json"],
        "llm_providers": llm_providers or {"version":"v1","primary":{"name":"openai","model":"gpt-4o-mini","api_key_env":"OPENAI_API_KEY","timeout_sec":35},"fallback":{"name":"gemini","model":"gemini-2.0-flash","api_key_env":"GEMINI_API_KEY","timeout_sec":35},"policy":{"max_retries":1,"circuit_break_after":3,"dry_run_if_unavailable": true}},
        "retriever_config": retriever_cfg or {"version":"v1","python_exe":"python","entrypoint":"rag_step5_retrieve.py","rag_project_path":"./rag","default_threshold":"strict","default_k":8,"filters":{"role_level":"junior","domain":"tech"},"timeout_sec":40}
    }
    load_report = {"ok": True, "inactive_refs": inactive_refs}
    return env, load_report


def _try_load_optional(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
