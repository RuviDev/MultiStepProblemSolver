#!/usr/bin/env python3
# Phase 1 — Quick Skim (taxonomy proposal)
import re, json, sys
from pathlib import Path
from collections import Counter

STOP_ACRONYMS = set("""PDF URL HTTP HTTPS API SQL CPU GPU AI ML NLP UI UX LLM RAG JSON CSV YAML XML DOC ID KPI OKR ETA TBD TBC ETC TTL UTC GMT IST UTC+ WE OSS SAAS PaaS IaaS SSO MFA OTP KPI KPIE ETL ELT DAG DAGs NDA POC MVP ROI""".split())

ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")
BATCH_RE = re.compile(r"(?i)\bBatch\s*(\d+)\b")

def main():
    base = Path(__file__).resolve().parents[1]
    out = base / "0_phase0" / "taxonomy_proposed.json"
    docling_dir = base / "2_docling"

    if not docling_dir.exists():
        print("Run phase1_docling_ingest.py first.", file=sys.stderr)
        sys.exit(1)

    acr_counter = Counter()
    batch_numbers = set()
    per_doc = {}

    for doc_dir in sorted(docling_dir.glob("DOC*")):
        md_files = sorted(doc_dir.glob("*.md"))
        if not md_files:
            continue

        text = ""
        for m in md_files:
            try:
                text += m.read_text(encoding="utf-8") + "\n"
            except Exception:
                pass

        acrs = [a for a in ACRONYM_RE.findall(text) if a not in STOP_ACRONYMS]
        acr_counter.update(acrs)
        batches = [int(n) for n in BATCH_RE.findall(text)]
        batch_numbers.update(batches)

        per_doc[doc_dir.name] = {
            "top_acronyms": Counter(acrs).most_common(20),
            "found_batches": sorted(set(batches)),
            "chars_scanned": len(text)
        }

    proposed = {
        "acronyms": {k: "" for k, _ in acr_counter.most_common(50)},
        "batches": {
            "pattern": r"(?i)\bBatch\s*(\d+)\b" if batch_numbers else "",
            "min": min(batch_numbers) if batch_numbers else None,
            "max": max(batch_numbers) if batch_numbers else None
        },
        "synonyms": {},
        "per_doc_snapshot": per_doc,
        "notes": "Fill the full forms for acronyms; copy what you want into taxonomy.json."
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(proposed, f, indent=2)

    print("Wrote proposal to", out)

if __name__ == "__main__":
    main()
