import json
from typing import Dict, Any, List
from .llm_orchestrator import generate_with_fallback

def _active_problem(ts: Dict[str,Any]) -> Dict[str,Any] | None:
    prs = ts.get("problem_records", [])
    if not prs:
        return None
    prs_sorted = sorted(prs, key=lambda p: p.get("last_updated",""), reverse=True)
    return prs_sorted[0]

def _role_title(role_catalog: Dict[str,Any], role_id: str) -> str:
    for r in (role_catalog or {}).get("roles", []):
        if r.get("id") == role_id:
            return r.get("title") or role_id
    return role_id or ""

def _pp_titles(gpp: Dict[str,Any], ids: List[str]) -> List[str]:
    by_id = {p["id"]: p for p in (gpp or {}).get("pain_points", [])}
    return [by_id.get(pid, {}).get("title", pid) for pid in (ids or [])]

def _format_sources(evidence: List[Dict[str,Any]]) -> str:
    if not evidence:
        return "—"
    lines = []
    for it in evidence:
        aid = it.get("anchor_id","?")
        page = it.get("page")
        doc = it.get("source_doc","vault")
        lines.append(f"[{aid}] — {doc}{' p.'+str(page) if page else ''}")
    return "\n".join(lines)

def _evidence_bullets(evidence: List[Dict[str,Any]]) -> str:
    if not evidence:
        return "No in-vault passages found."
    return "\n".join([f"- {it.get('snippet','').strip()} [{it.get('anchor_id')}]" for it in evidence])

def _insight_lines(insights: Dict[str,Any]) -> List[str]:
    if not insights:
        return []
    lines = []
    for k,v in insights.items():
        val = v.get("value")
        conf = v.get("confidence")
        try:
            lines.append(f"{k}={val} (c={float(conf):.2f})")
        except Exception:
            lines.append(f"{k}={val} (c={conf})")
    return lines[:12]

def _build_system_prompt(pcc: Dict[str,Any]) -> str:
    tone = pcc.get("tone","neutral")
    fmt = pcc.get("format","markdown")
    struct = pcc.get("structure", [])
    return (
        "You are the Composer for a career-planning assistant. "
        "Follow the user's PCC (Prompt Control Card). "
        f"Tone: {tone}. Output format: {fmt}. "
        f"Sections (use exact headings): {', '.join(struct)}. "
        "Citations must be inline using bracketed anchor IDs like [BND–GPP-...]. "
        "Never invent sources; use only the provided evidence anchors. "
        "If evidence is missing for a claim, use generic language and do not cite."
    )

def _build_user_prompt(env: Dict[str,Any],
                       ts: Dict[str,Any],
                       step1: Dict[str,Any],
                       step2: Dict[str,Any],
                       step5: Dict[str,Any],
                       step6: Dict[str,Any],
                       step7: Dict[str,Any]) -> str:
    role_id = (step2.get("problem_context",{}) or {}).get("employment_category")
    role_title = _role_title(env.get("catalog_data",{}).get("role_catalog",{}), role_id)
    pp_ids = (step2.get("problem_context",{}) or {}).get("pain_points", [])
    pp_titles = _pp_titles(env.get("catalog_data",{}).get("gpp_taxonomy",{}), pp_ids)
    pr = _active_problem(ts) or {}
    insights = pr.get("insights", {})
    evidence = step6.get("results", []) or []

    parts = []
    parts.append("=== USER PROMPT ===")
    parts.append(step1.get("request_envelope",{}).get("prompt_clean","").strip())
    parts.append("\n=== CONTEXT ===")
    parts.append(f"Role: {role_title} ({role_id})")
    parts.append(f"Pain Points: {', '.join(pp_titles) or '—'}")
    if insights:
        lines = []
        for k,v in insights.items():
            try:
                lines.append(f"{k}={v.get('value')} (c={float(v.get('confidence',0)):.2f})")
            except Exception:
                lines.append(f"{k}={v.get('value')} (c={v.get('confidence')})")
            if len(lines) >= 12:
                break
        parts.append("Insights: " + "; ".join(lines))
    else:
        parts.append("Insights: —")
    parts.append("\n=== EVIDENCE (anchors) ===")
    for it in evidence[:8]:
        parts.append(f"[{it.get('anchor_id')}] {it.get('snippet','').strip()}")

    parts.append("\n=== RULES ===")
    pcc = step5.get("pcc",{})
    parts.append(f"Answerability: {pcc.get('answerability')}")
    parts.append("Cite only with provided anchors like [ANCHOR_ID]. If unsure, say so; do not fabricate.")
    parts.append("Use the exact section headings from PCC.structure.")
    parts.append("End with a 'Sources' section listing each cited anchor once (anchor_id + doc + page).")

    return "\n".join(parts)

def _fallback_missing_from_taxonomy(env: Dict[str,Any], ts: Dict[str,Any]) -> list[str]:
    """
    Conservative fallback when PCC.missing_fields is empty (e.g., pain_points not bound yet).
    Used ONLY to pick the up-to-N clarifier questions. Does not alter PCC.
    """
    pr = _active_problem(ts) or {}
    insights = pr.get("insights", {}) or {}

    # Pain points → default to capability_shortfall if unset
    pain_points = ((pr.get("problem_context") or {}).get("pain_points") or [])[:]
    if not pain_points:
        pain_points = ["gpp.capability_shortfall"]

    # required categories from taxonomy
    pain_tax = env.get("pain_taxonomy", {})
    req_cats = []
    by_id = {pp.get("id"): pp for pp in (pain_tax.get("pain_points", []) or [])}
    for pid in pain_points:
        node = by_id.get(pid, {})
        req_cats.extend(node.get("requires_insights", []) or [])
    req_cats = list(dict.fromkeys(req_cats))  # dedupe

    # catalog children
    git_cat = (env.get("catalog_data", {}) or {}).get("git_insight_catalog", {}) or {}
    children = []
    for node in git_cat.get("fields", []) or []:
        if node.get("id") in req_cats:
            for ch in node.get("children", []) or []:
                if ch.get("id"):
                    children.append(ch.get("id"))

    # threshold from policy.survey to decide if we already "have enough"
    policy = env.get("thread_policy", {}) or {}
    min_conf = float(((policy.get("survey") or {}).get("min_confidence_to_skip", 0.7)))
    missing = []
    for fid in children:
        rec = insights.get(fid)
        if not rec or (rec.get("confidence", 0) < min_conf):
            missing.append(fid)
    return missing

def _llm_rewrite_clarifiers(env: Dict[str, Any],
                            ts: Dict[str, Any],
                            questions: List[Dict[str, Any]],
                            step1: Dict[str, Any],
                            step2: Dict[str, Any]) -> str:
    """
    Presentation-only: rewrite survey questions (and show current answers when present).
    Does NOT change field_ids or canonical options. Never invents answers.
    """
    try:
        policy = env.get("thread_policy", {}) or {}
        survey_cfg = policy.get("survey", {}) or {}
        if not bool(survey_cfg.get("llm_rewrite", True)):
            return ""

        from .llm_orchestrator import generate_with_fallback

        # Collect current answers (if any) for these question field_ids
        pr = _active_problem(ts) or {}
        current = {}
        for q in questions:
            fid = q.get("field_id")
            rec = (pr.get("insights", {}) or {}).get(fid)
            if rec and "value" in rec:
                current[fid] = {
                    "value": rec.get("value"),
                    "source": rec.get("source"),
                    "confidence": rec.get("confidence")
                }

        sys_lines = [
            "You are rewriting survey questions for clarity and friendliness.",
            "CONSTRAINTS:",
            "- Do NOT add or remove questions.",
            "- Do NOT add or remove options.",
            "- Do NOT change the meaning of options.",
            "- If a current_answer is provided, SHOW it explicitly (e.g., 'Currently set: X').",
            "- If NO current_answer, present either the options (for enum) or a short single-line input cue (for text).",
            "- Do NOT invent answers.",
            "OUTPUT FORMAT (strict):",
            "Return ONE JSON object only:",
            "{\"render\": \"<markdown>\"}",
            "Where <markdown> is a compact list of questions in friendly language with any current answers shown.",
            "No commentary outside that single JSON object."
        ]

        ctx_role = (step2.get("problem_context", {}) or {}).get("employment_category", "")
        ctx_pain = ", ".join((step2.get("problem_context", {}) or {}).get("pain_points", []) or [])

        prompt_lines = [f"ROLE: {ctx_role}", f"PAIN_POINTS: {ctx_pain}", "QUESTIONS:"]
        for q in questions:
            fid = q.get("field_id","")
            label = q.get("label","")
            typ = q.get("type","text")
            opt = q.get("options", [])
            ca = current.get(fid)
            prompt_lines.append(f"- field_id: {fid}")
            prompt_lines.append(f"  type: {typ}")
            prompt_lines.append(f"  label: {label}")
            if opt:
                prompt_lines.append(f"  options: {', '.join(map(str,opt))}")
            if ca:
                prompt_lines.append(f"  current_answer: {json.dumps(ca.get('value'))} (source={ca.get('source')}, conf={ca.get('confidence')})")
            else:
                prompt_lines.append(f"  current_answer: <none>")

        system_prompt = "\n".join(sys_lines)
        user_prompt = "\n".join(prompt_lines)[:5000]

        llm_cfg = env.get("llm_providers", {}) or {}
        res = generate_with_fallback(llm_cfg, system_prompt, user_prompt) or {}
        content = (res.get("content","") or "").strip()

        data = json.loads(content) if content else {}
        render = (data.get("render","") or "").strip()
        if not render:
            return ""
        return render[:4000]
    except Exception:
        return ""

def compose_and_persist(env: Dict[str, Any],
                        ts: Dict[str, Any],
                        step1: Dict[str, Any],
                        step2: Dict[str, Any],
                        step5: Dict[str, Any],
                        step6: Dict[str, Any],
                        step7: Dict[str, Any]) -> Dict[str, Any]:
    """
    UAA-only composer:
    - Calls the LLM whenever retrieval produced evidence (UAA informational answer).
    - Forbids plan/roadmap/timeline output while planning agent is disabled.
    - Shows at most N (policy) Quick clarifiers only when the user intent is 'plan'.
    - LLM rewrites clarifier questions and shows current answers when present (presentation-only).
    - Falls back to a rule-based evidence draft if the LLM returns empty or when no evidence exists.
    """
    pcc = step5.get("pcc", {}) or {}
    evidence = step6.get("results", []) or []
    ans = pcc.get("answerability", "unknown")

    # Policy + intent
    policy = env.get("thread_policy", {}) or {}
    ask_only_on_plan = bool(policy.get("ask_insights_only_if_intent_is_plan", True))
    max_q = int(policy.get("max_insight_questions_per_turn", 2))
    disallow_planning = bool(policy.get("disallow_planning_in_uaa", True))
    planning_agent_enabled = bool(policy.get("planning_agent_enabled", False))
    survey_cfg = policy.get("survey", {}) or {}
    use_missing_fallback = bool(survey_cfg.get("use_missing_fallback", True))

    intent = (step1.get("request_envelope", {}) or {}).get("intent", "learn")
    struct = pcc.get("structure", ["Preface", "Core Summary", "Evidence", "Checklist", "Closer", "Sources"])

    def _rule_based(md_preface: str = None, include_checklist: bool = False, missing_fields: list = None) -> str:
        def sec(name): return f"# {name}\n"
        md = []
        if "Preface" in struct:
            md.append(sec("Preface") + (md_preface or "We have enough to give a directional answer, but a few items are still missing."))
        if "Core Summary" in struct:
            role_id = (step2.get("problem_context", {}) or {}).get("employment_category", "")
            pain = ", ".join((step2.get("problem_context", {}) or {}).get("pain_points", [])) or "—"
            md.append(sec("Core Summary") + f"Mapped role: **{role_id}**. Detected pain points: {pain}.")
        if "Evidence" in struct:
            md.append(sec("Evidence") + (_evidence_bullets(evidence)))
        if "Checklist" in struct and include_checklist:
            if missing_fields:
                bullets = "\n".join([f"- Provide: `{f}`" for f in missing_fields])
                md.append(sec("Checklist") + "To proceed, please provide:\n" + bullets)
            else:
                md.append(sec("Checklist") + "No critical items pending.")
        if "Closer" in struct:
            md.append(sec("Closer") + "If you want a tailored plan next, I can ask 1–2 quick clarifiers and then proceed.")
        if "Sources" in struct:
            md.append(sec("Sources") + _format_sources(evidence))
        return "\n\n".join(md)

    # If we have evidence, try LLM (UAA informational answer).
    if evidence:
        system_prompt = _build_system_prompt(pcc)

        # UAA guardrails (do NOT produce plans or time-boxed roadmaps)
        if disallow_planning and not planning_agent_enabled:
            guardrails = [
                "You are in UAA (Understanding & Answering) mode only.",
                "DO NOT produce plans, roadmaps, schedules, timelines, or time-boxed breakdowns (e.g., 'Month 1/2/3', 'Week 1..n', 'Day 1..n').",
                "If the user asks to plan, do not plan yet. Provide an evidence-grounded informational answer and, if appropriate, ask up to "
                f"{max_q} very short clarifying questions to prepare for planning later.",
                "Use retrieved evidence as knowledge to synthesize a cohesive answer in your own words; do NOT copy bullet lists verbatim. "
                "Weave the key points into the answer and cite [ANCHOR_ID] inline where relevant.",
                "At the end, list sources under a 'Sources' heading. Do not repeat the raw evidence text there; just the citations."
            ]
            system_prompt = system_prompt + "\n\n" + "\n".join(f"CONSTRAINT: {c}" for c in guardrails)

        user_prompt = _build_user_prompt(env, ts, step1, step2, step5, step6, step7)

        llm_cfg = env.get("llm_providers", {}) or {}
        gen = generate_with_fallback(llm_cfg, system_prompt, user_prompt)
        provider = gen.get("provider", "unknown")
        content = (gen.get("content", "") or "").strip()

        # If the model returned empty content, fall back to a rule-based draft (no checklist spam)
        if not content:
            content = _rule_based(md_preface="Model response was empty; returning evidence-aligned draft.",
                                  include_checklist=False,
                                  missing_fields=None)

        # Append Quick clarifiers only if user intent is to plan AND policy allows
        missing_fields = pcc.get("missing_fields", []) or []
        if not missing_fields and use_missing_fallback:
            missing_fields = _fallback_missing_from_taxonomy(env, ts)

        if missing_fields and (not ask_only_on_plan or intent == "plan"):
            try:
                from agent.survey_io import export_current_survey  # local import to avoid cycles
                qs = export_current_survey(env, ts, missing_fields) or {}
                pr = _active_problem(ts) or {}
                already = set(pr.get("asked_fields") or [])
                ask = [q for q in (qs.get("questions", []) or [])
                       if q.get("field_id") and q["field_id"] not in already][:max_q]
                if ask:
                    # LLM rephrases questions and shows current answers if present
                    friendly = _llm_rewrite_clarifiers(env, ts, ask, step1, step2)
                    if friendly:
                        content = content + "\n\n# Quick clarifiers\n" + friendly
                    else:
                        # Fallback to plain bullets
                        clar = ["", "# Quick clarifiers"]
                        for q in ask:
                            label = q.get("label", q.get("field_id", ""))
                            opts = q.get("options", [])
                            if opts:
                                clar.append(f"- {label}  " + " / ".join(opts))
                            else:
                                clar.append(f"- {label}")
                        content = content + "\n" + "\n".join(clar)
                    # mark asked
                    new_ids = [q["field_id"] for q in ask]
                    pr.setdefault("asked_fields", [])
                    for fid in new_ids:
                        if fid not in pr["asked_fields"]:
                            pr["asked_fields"].append(fid)
            except Exception:
                # Never block the answer on clarifier rendering
                pass

        # Ensure Sources at the end (LLM may omit the section header)
        if "Sources" in struct and evidence and "# Sources" not in content:
            content = content + "\n\n# Sources\n" + _format_sources(evidence)

    else:
        # No evidence → rule-based informational draft only (UAA), no plan, no checklist spam
        provider = "rule_based"
        content = _rule_based(md_preface="I couldn't retrieve supporting evidence right now. Here’s a concise, best-effort summary.",
                              include_checklist=False,
                              missing_fields=None)

    # Persist to ProblemRecord
    pr = _active_problem(ts) or {}
    pr.setdefault("generation_history", [])
    pr["last_response"] = {
        "provider": gen.get("provider", "openai") if evidence else "rule_based",
        "pcc_answerability": ans,
        "markdown": content[:120000]
    }
    pr["generation_history"].append({"provider": pr["last_response"]["provider"]})
    pr["generation_history"] = pr["generation_history"][-10:]

    # Write back (replace the active problem)
    if ts.get("problem_records"):
        active_id = pr.get("problem_id")
        replaced = False
        for i, rec in enumerate(ts["problem_records"]):
            if rec.get("problem_id") == active_id:
                ts["problem_records"][i] = pr
                replaced = True
                break
        if not replaced:
            ts["problem_records"][-1] = pr

    return {"ok": True,
            "provider": pr["last_response"]["provider"],
            "answerability": ans,
            "chars": len(content),
            "markdown": content}
