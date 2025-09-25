#!/usr/bin/env python3
import os, json, argparse
from agent.config_loader import build_environment_context
from agent.pcc_builder import build_pcc
from agent.retrieval_adapter import retrieve_and_attach
from agent.history_manager import update_and_persist_history
from agent.composer import compose_and_persist
from agent.survey_io import apply_survey_answers

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config_dir", default=os.path.join("config"))
    ap.add_argument("--state_path", default=os.path.join("state", "thread_state.json"))
    ap.add_argument("--answers", required=True, help="Path to JSON: {'problem_id': '...', 'fields': {...}}")
    ap.add_argument("--out_dir", default="out")
    args = ap.parse_args()

    # Load env & state
    env, _ = build_environment_context(args.config_dir)
    with open(args.state_path, "r", encoding="utf-8") as f:
        ts = json.load(f)

    # Apply answers → insights
    answers = json.load(open(args.answers, "r", encoding="utf-8"))
    res_apply = apply_survey_answers(ts, answers)
    with open(args.state_path, "w", encoding="utf-8") as f:
        json.dump(ts, f, ensure_ascii=False, indent=2)

    # Re-run Steps 5→8 to strengthen answerability with the new insights
    res5 = build_pcc(env, ts, {"ok": True}, {"ok": True}, {"ok": True})
    res6 = retrieve_and_attach(env, ts, {"ok": True, "request_envelope": {"prompt_clean": ""}}, {"ok": True}, res5)
    res7 = update_and_persist_history(env, ts, {"ok": True}, {"ok": True}, {"ok": True}, {"ok": True}, res5, res6)
    res8 = compose_and_persist(env, ts, {"ok": True, "request_envelope": {"prompt_clean": ""}}, {"ok": True}, res5, res6, res7)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "final_response.md"), "w", encoding="utf-8") as f:
        f.write(res8.get("markdown", ""))
    with open(os.path.join(args.out_dir, "final_response.json"), "w", encoding="utf-8") as f:
        json.dump({
            "provider": res8.get("provider"),
            "answerability": res8.get("answerability"),
            "chars": res8.get("chars")
        }, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": True,
        "applied": res_apply.get("updated", 0),
        "provider": res8.get("provider")
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
