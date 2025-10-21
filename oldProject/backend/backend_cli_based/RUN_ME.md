# Agentic AI System — How to Run (and what to change)

This repo contains two pieces:
- **`agent8/`** – the agentic pipeline (receiver → scope map → problem select → UIA → PCC → retrieval → history → composer → readiness).
- **RAG project at repo root** – `configs/` and `vault_index/` used by the retriever (BM25 + embeddings + MMR + compression).

---

## 0) One-time fixes you MUST do

1) **Fix the retriever path (already patched here):**
   - `agent8/config/retriever.json` → `"rag_project_path": "<path to this repo root>"`  
     In this copy it's set to the absolute sandbox path. On your PC, change it to your local repo folder, e.g.  
     `C:\\Users\\you\\Projects\\agentic_ai` (Windows) or `/Users/you/Projects/agentic_ai` (macOS/Linux).

2) **Do NOT store API keys in JSON:**
   - `agent8/config/llm_providers.json` currently has placeholders in `api_key_env` fields. The code **does not read** these.
   - Instead, set environment variables:
     - `OPENAI_API_KEY` (for OpenAI models)
     - `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) (for Google Gemini models)
   - Recommendation: replace any real keys in JSON with `"api_key_env": "ENV"` or remove the field.

3) **Windows UTF-8 (only for cmd.exe):**
   - If you run into weird characters, enable UTF‑8 once per session:
     ```cmd
     set PYTHONUTF8=1
     set PYTHONIOENCODING=utf-8
     chcp 65001
     ```

---

## 1) Python version

- Use **Python 3.10–3.11**. (The repo has `__pycache__` for 3.11.)

---

## 2) Install dependencies

From the repo root:

### macOS/Linux (bash)
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **Notes**
> - `faiss-cpu` is optional but recommended because `vault_index/faiss.index` exists.
> - `sentence-transformers` will download the embedding model listed in `configs/config.yml` (`intfloat/e5-small-v2` by default).
> - If you **don't** set API keys or skip installs, the agent still runs in **dry-run** mode and will produce a layered draft without citations.

---

## 3) Set environment variables (only if you want real LLM calls)

### macOS/Linux (bash)
```bash
export OPENAI_API_KEY="sk-..."
# or Gemini:
export GEMINI_API_KEY="AIza..."
```

### Windows (PowerShell)
```powershell
$env:OPENAI_API_KEY="sk-..."
# or Gemini:
$env:GEMINI_API_KEY="AIza..."
```

---

## 4) Run it

From the **repo root** (so `rag_step5_retrieve.py` is visible):

### Example
```bash
python agent8/main.py \
  --config_dir agent8/config \
  --state_path agent8/state/thread_state.json \
  --out agent8/out/request_envelope.json \
  --prompt "I want a junior data analyst job; my path is fuzzy and I keep switching courses."
```

Outputs (under `agent8/out/` and `agent8/state/`):
- `out/request_envelope.json` – full pipeline I/O snapshot
- `out/final_response.md` – final composed answer (with inline `[ANCHOR_ID]` citations when retrieval succeeds)
- `out/final_response.json` – provider + answerability meta
- `state/thread_state.json` – persistent conversation state
- `readiness.json` – what the UIA Stage‑2 believes is still missing

> **Tip:** run the same command again with a different `--prompt`; the system keeps per‑thread history and will adapt the plan + memory.

---

## 5) Common issues & fixes

- **`NO_API_KEY` / OpenAI or Gemini errors**
  - Set the env var(s) as above. The system will automatically fall back to Gemini, then to *dry-run* if keys are missing.

- **Retriever returns 0 evidence**
  - Ensure `agent8/config/retriever.json` has `rag_project_path` pointing to **repo root** (where `configs/` and `vault_index/` live).
  - Ensure `rank-bm25`, `sentence-transformers` (and ideally `faiss-cpu`) are installed.
  - Check `configs/config.yml` thresholds and filters; try `lenient` by changing `default_threshold` in `agent8/config/retriever.json` to `"lenient"`.

- **Windows path / entrypoint not found**
  - Keep `entrypoint: "rag_step5_retrieve.py"` and set `rag_project_path` to the **repo root**. The code runs the retriever with `cwd=rag_project_path`.

- **Garbled Unicode on Windows**
  - Run the UTF‑8 commands from step 0.3.

---

## 6) What changed from your older runs (recommended updates)

- **Fixed retriever path**: was a hard‑coded Windows path; now uses your repo path.
- **Use env vars for keys**: the code already expects `OPENAI_API_KEY` / `GEMINI_API_KEY`. Avoid secrets in JSON.
- **Pinned dependencies**: see `requirements.txt`; this enables the full retrieval pipeline.
- **Consistent entrypoint**: `rag_step5_retrieve.py` lives in repo root; keep `cwd=rag_project_path` = repo root.

---

## 7) Nice-to‑have next steps (optional)

- Update `agent8/config/role_catalog.json` with your real roles/titles.
- Add anchors to `agent8/config/vault_index.json` if you want clickable source metadata.
- Tune `configs/config.yml` (`final_k`, thresholds) and `pcc_defaults.json` (target tokens, tone) to your app.
