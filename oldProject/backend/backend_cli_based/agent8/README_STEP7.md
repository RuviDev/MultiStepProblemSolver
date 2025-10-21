# Step 7 — Conversation State & History (minimal memory)

What this adds:
- Rolling `history_summary` (last ~2000 chars of user prompts, timestamped).
- Per-ProblemRecord `dialogue_snippets[]` (last 25 turns): prompt, mapped role/PP, mapping_confidence, answerability, missing_fields, survey_len, evidence anchors.
- Compact `planning_brief` text on the active ProblemRecord for UPA/Composer to read.

Where it lives:
- `state/thread_state.json`
  - `history_summary`
  - `problem_records[n].dialogue_snippets[]`
  - `problem_records[n].planning_brief`

Output:
- `out/request_envelope.json` → `step7` with counts and a copy of the `planning_brief` for visibility.

Notes:
- No LLM used here (deterministic). Safe to run offline.
- You can grow `planning_brief` later (e.g., include top evidence anchors).
