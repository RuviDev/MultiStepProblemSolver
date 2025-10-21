# Step 8 — Generation Protocol (LLM orchestration + composer)

- Configure `config/llm_providers.json` and set your env vars:
  - `OPENAI_API_KEY`, `GEMINI_API_KEY`

- Run:
  ```bash
  python main.py --prompt "I want a junior data analyst job; my path is fuzzy and I keep switching courses."
  ```

- Outputs created:
  - `out/request_envelope.json` (full pipeline outputs)
  - `out/final_response.md` (renderable answer with inline [ANCHOR_ID] citations or rule-based draft)
  - `out/final_response.json` (provider, answerability, char length)
  - `state/thread_state.json` (persisted ProblemRecord.last_response)
