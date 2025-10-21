#!/usr/bin/env python3
import os, json, argparse
from agent.config_loader import build_environment_context
from agent.receiver import receive_prompt
from agent.scope_map import scope_gate_and_map
from agent.problem_select import problem_selection_and_binding
from agent.uia_stage1 import uia_stage1_extract_and_draft
from agent.pcc_builder import build_pcc
from agent.retrieval_adapter import retrieve_and_attach
from agent.history_manager import update_and_persist_history
from agent.composer import compose_and_persist
from agent.survey_io import export_current_survey, apply_survey_answers  # Step 9
from agent.uia_stage2 import readiness_check
from agent.memory_manager import load_profile, save_profile, update_profile_from_turn  # Step 12

def _bootstrap_state_if_missing(state_path: str):
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    if not os.path.exists(state_path):
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"history_summary": "", "problem_records": []}, f, ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config_dir", default=os.path.join("config"))
    ap.add_argument("--state_path", default=os.path.join("state","thread_state.json"))
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--answers_json", default=None)  # optional: apply survey answers inline on this turn
    ap.add_argument("--out", default=os.path.join("out","request_envelope.json"))
    args = ap.parse_args()

    # Ensure state exists
    _bootstrap_state_if_missing(args.state_path)

    # Step 0 — Environment & Artifacts
    env, report = build_environment_context(args.config_dir)
    # Load cross-thread user profile (non-sensitive prefs)
    prof = load_profile()
    env['user_profile'] = prof

    # Load state (fresh)
    with open(args.state_path, "r", encoding="utf-8") as f:
        thread_state = json.load(f)

    # Optional: apply survey answers inline BEFORE building PCC/retrieval/composer
    if args.answers_json:
        try:
            inline_answers = json.load(open(args.answers_json, "r", encoding="utf-8"))
            _ = apply_survey_answers(thread_state, inline_answers)
            with open(args.state_path, "w", encoding="utf-8") as f:
                json.dump(thread_state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Step 1 — Receive
    res1 = receive_prompt(env, thread_state, args.prompt)

    # Step 2 — Scope & Map
    res2 = scope_gate_and_map(env, res1["request_envelope"] if res1.get("ok") else {})

    # Step 3 — Problem select/bind
    res3 = problem_selection_and_binding(env, thread_state, res2)
    if res3.get("ok"):
        with open(args.state_path, "w", encoding="utf-8") as f:
            json.dump(thread_state, f, ensure_ascii=False, indent=2)

    # Step 4 — UIA Stage-1
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts2 = json.load(f)
    res4 = uia_stage1_extract_and_draft(env, ts2, res1, res3)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts2, f, ensure_ascii=False, indent=2)

    # Step 5 — PCC
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts3 = json.load(f)
    res5 = build_pcc(env, ts3, res2, res3, res4)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts3, f, ensure_ascii=False, indent=2)

    # Step 6 — Retrieval
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts4 = json.load(f)
    res6 = retrieve_and_attach(env, ts4, res1, res2, res5)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts4, f, ensure_ascii=False, indent=2)

    # Step 7 — History
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts5 = json.load(f)
    res7 = update_and_persist_history(env, ts5, res1, res2, res3, res4, res5, res6)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts5, f, ensure_ascii=False, indent=2)

    # Step 8 — Compose/Generate
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts6 = json.load(f)
    res8 = compose_and_persist(env, ts6, res1, res2, res5, res6, res7)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts6, f, ensure_ascii=False, indent=2)

    # Step 9 — Survey Export (persist survey schema and emit out/survey.json)
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts7 = json.load(f)
    s9 = export_current_survey(ts7, res4)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts7, f, ensure_ascii=False, indent=2)

    # Step 12 — Readiness Check (UIA Stage-2)
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts8 = json.load(f)
    s12 = readiness_check(env, ts8, res2, res5)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts8, f, ensure_ascii=False, indent=2)

    # --- record Stage-2 asked keys to avoid repeats next turns ---
    try:
        with open(args.state_path, 'r', encoding='utf-8') as f:
            ts_after12 = json.load(f)
        prs = ts_after12.get('problem_records') or []
        if prs:
            pr = prs[-1]
            s12_keys = (s12 or {}).get('survey', {}).get('required_keys') or []
            if s12_keys:
                from agent.survey_policy import current_turn_index, record_asked
                turn_idx = current_turn_index(ts_after12)
                record_asked(pr, list(dict.fromkeys(s12_keys)), turn_idx)
                with open(args.state_path, 'w', encoding='utf-8') as f:
                    json.dump(ts_after12, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # === Write outputs ===
    out_dir = os.path.dirname(args.out)
    os.makedirs(out_dir, exist_ok=True)

    # (A) Pipeline trace
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({
            "environment_load_report": report,
            "step1": res1, "step2": res2, "step3": res3, "step4": res4,
            "step5": res5, "step6": res6, "step7": res7, "step8": res8,
            "step9": s9, "step12": s12
        }, f, ensure_ascii=False, indent=2)

    # (B) Final response artifacts
    fr_md = os.path.join(out_dir, "final_response.md")
    fr_json = os.path.join(out_dir, "final_response.json")
    with open(fr_md, "w", encoding="utf-8") as f:
        f.write(res8.get("markdown", ""))
    with open(fr_json, "w", encoding="utf-8") as f:
        json.dump({
            "provider": res8.get("provider"),
            "answerability": res8.get("answerability"),
            "chars": res8.get("chars")
        }, f, ensure_ascii=False, indent=2)

    # (C) Survey payload for frontend (when present)
    survey_path = os.path.join(out_dir, "survey.json")
    try:
        with open(survey_path, "w", encoding="utf-8") as sf:
            json.dump(s9, sf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # (D) Readiness payload for frontend / UPA handoff
    readiness_path = os.path.join(out_dir, "readiness.json")
    try:
        with open(readiness_path, "w", encoding="utf-8") as rf:
            json.dump(s12, rf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(json.dumps({
        "ok": res1.get("ok") and res2.get("ok") and res3.get("ok", True) and res4.get("ok", True),
        "out": args.out
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
