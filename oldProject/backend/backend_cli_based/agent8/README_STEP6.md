# Step 6 — Retrieval & Evidence Pack

### Configure your RAG path
Edit **config/retriever.json**:
```json
{
  "version": "v1",
  "python_exe": "python",
  "entrypoint": "rag_step5_retrieve.py",
  "rag_project_path": "/path/to/your/rag",
  "default_threshold": "strict",
  "default_k": 8,
  "filters": {
    "role_level": "junior",
    "domain": "tech"
  },
  "timeout_sec": 40
}
```

Set `"rag_project_path"` to the folder where your RAG zip was unzipped (the folder that contains `rag_step5_retrieve.py`).

### How it works
- Builds a query from the user's prompt + role title + pain-point synonyms.
- Calls your retriever CLI:
  `python rag_step5_retrieve.py retrieve --project <rag_root> --q "<query>" --k <top_k> --threshold strict`
- Parses the **evidence_pack** and persists it under the active `ProblemRecord`:
  `problem_records[n].last_evidence_pack` and `evidence_history` (capped to 5).

### Run
```bash
python main.py --prompt "I want a junior data analyst job; my path is fuzzy and I keep switching courses."
cat out/request_envelope.json   # see step6.results and evidence_count
```

If the RAG path isn't set or the CLI fails, Step 6 returns `evidence_count: 0` and continues (cite-or-decline policy).
