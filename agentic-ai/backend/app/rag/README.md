# Agentic RAG — Phase 0 (Lite)

This folder is a tiny, content-agnostic setup so we can ingest safely in Phase 1.

## What’s here
- `1_raw_pdfs/` — Source PDFs (copied from your upload if found).
- `0_phase0/corpus_registry.csv` — Registry mapping stable `doc_id` ↔ file, with checksum and version (20251014).
- `0_phase0/metadata_schema.json` — Minimal chunk metadata contract (no content assumptions).
- `0_phase0/taxonomy.json` — Intentionally empty; fill in Phase 1 after a quick skim.

## Next (Phase 1)
- Convert PDFs using Docling.
- Skim content and then populate taxonomy/batch detection where appropriate.
- Generate chunks and attach metadata from `metadata_schema.json`.
