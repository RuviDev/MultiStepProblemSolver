#!/usr/bin/env python3
# (see file header for usage)
# pip install docling pandas pypdf

# Phase 1 — Docling ingestion
import argparse, sys, csv, json, hashlib
from pathlib import Path
from datetime import datetime

def sha256sum(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def page_count_pdf(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return None

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def to_markdown_and_json(converter, pdf_path: Path):
    result = converter.convert(str(pdf_path))
    candidates = []
    for attr in ("document", "doc", "output", "result"):
        if hasattr(result, attr):
            candidates.append(getattr(result, attr))
    candidates.append(result)

    md, js = None, None
    md_methods = ["as_markdown", "to_markdown", "export_to_markdown"]
    js_methods = ["as_json", "to_json", "export_to_dict", "to_dict"]

    for obj in candidates:
        if md is None:
            for m in md_methods:
                if hasattr(obj, m):
                    md = getattr(obj, m)()
                    break
        if js is None:
            for m in js_methods:
                if hasattr(obj, m):
                    js = getattr(obj, m)()
                    break
        if md is not None and js is not None:
            break

    if isinstance(js, str):
        try:
            js = json.loads(js)
        except Exception:
            js = {"raw_json": js}

    if md is None:
        raise RuntimeError("Could not obtain Markdown from Docling result (API mismatch).")
    if js is None:
        js = {"warning": "JSON export method not found; minimal payload only."}

    if not isinstance(md, str):
        try:
            md = md[0]
        except Exception:
            md = str(md)
    return md, js

def build_converter():
    try:
        from docling.document_converter import DocumentConverter
        return DocumentConverter()
    except Exception as e:
        print("ERROR: Could not import/initialize Docling. Install it with:", file=sys.stderr)
        print("  pip install docling", file=sys.stderr)
        print("Original error:", e, file=sys.stderr)
        sys.exit(2)

def read_registry(registry_csv: Path):
    rows = []
    import csv
    with open(registry_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if str(r.get("is_current", "true")).lower() in ("true", "1", "yes"):
                rows.append(r)
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=None, help="Process only these DOCIDs (e.g., DOC01 DOC03).")
    parser.add_argument("--rebuild", action="store_true", help="Re-convert even if outputs exist.")
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[1]
    registry_csv = base / "0_phase0" / "corpus_registry.csv"
    out_root = base / "2_docling"

    if not registry_csv.exists():
        print("Registry not found at", registry_csv, file=sys.stderr)
        sys.exit(1)

    rows = read_registry(registry_csv)
    if args.only:
        rows = [r for r in rows if r["doc_id"] in set(args.only)]

    converter = build_converter()

    manifest_path = out_root / "manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as mf:
        pass  # truncate

    for r in rows:
        doc_id = r["doc_id"]
        version = r.get("version") or datetime.utcnow().strftime("%Y%m%d")
        rel = r["filename"]
        pdf_path = base / rel
        if not pdf_path.exists():
            print(f"[{doc_id}] Missing file: {pdf_path}", file=sys.stderr)
            continue

        out_dir = out_root / doc_id
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{doc_id}_{version}.md"
        json_path = out_dir / f"{doc_id}_{version}.json"
        stats_path = out_dir / "stats.json"

        if not args.rebuild and md_path.exists() and json_path.exists():
            print(f"[{doc_id}] Skipping (already exists). Use --rebuild to force.")
            continue

        print(f"[{doc_id}] Converting {pdf_path.name} → Markdown + JSON ...")
        try:
            md, js = to_markdown_and_json(converter, pdf_path)
        except Exception as e:
            print(f"[{doc_id}] Docling conversion failed: {e}", file=sys.stderr)
            continue

        md_path.write_text(md, encoding="utf-8")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(js, f, ensure_ascii=False, indent=2)

        pc = page_count_pdf(pdf_path)
        bytes_md = md_path.stat().st_size
        checksum = sha256sum(pdf_path)

        stats = {
            "doc_id": doc_id,
            "version": version,
            "filename": rel,
            "page_count": pc,
            "bytes_markdown": bytes_md,
            "checksum_pdf": checksum,
            "converted_at": datetime.utcnow().isoformat() + "Z"
        }
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        with open(out_root / "manifest.jsonl", "a", encoding="utf-8") as mf:
            mf.write(json.dumps(stats) + "\n")

        print(f"[{doc_id}] OK  → {md_path.name}, {json_path.name}")

    print("Done. Outputs under 2_docling/. Manifest at 2_docling/manifest.jsonl")

if __name__ == "__main__":
    main()
