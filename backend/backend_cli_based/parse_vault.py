#!/usr/bin/env python3
"""
Step 2: Parse & chunk the vault PDF(s) into anchor-based chunks.

Usage:
  python parse_vault.py --project ./rag_project --pdf "Research Article 03.pdf" --version v1

Outputs (under <project>/vault_index/):
  - chunks.jsonl           # one JSON object per chunk
  - parse_report.json      # summary (pages, anchors_found, chunks_written)
  - parse_log.jsonl        # warnings/info logs

Requirements:
  pip install pdfplumber PyPDF2 pyyaml
"""

import argparse, re, json, datetime, os, sys
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def load_yaml(p: Path):
    if yaml is None:
        # Minimal fallback: not parsing YAML, just return raw string
        return {"_raw_text": p.read_text(encoding="utf-8")}
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def extract_pages_text(pdf_path: Path):
    pages = []
    backend = "none"
    # Try pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                pages.append((i+1, t))
        if any(t for _,t in pages):
            return pages, "pdfplumber"
    except Exception as e:
        pass
    # Fallback PyPDF2
    try:
        import PyPDF2
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for i, p in enumerate(reader.pages):
                t = p.extract_text() or ""
                pages.append((i+1, t))
        if any(t for _,t in pages):
            return pages, "PyPDF2"
    except Exception as e:
        pass
    return [], "none"

def build_doc_with_page_offsets(pages_text):
    """Join pages with markers so we can approximate page ranges per chunk."""
    parts = []
    page_offsets = []  # (page_num, start, end)
    cur = 0
    for page_num, txt in pages_text:
        header = f"\n<<<PAGE {page_num}>>>\n"
        parts.append(header); cur += len(header)
        parts.append(txt); start = cur; cur += len(txt)
        page_offsets.append((page_num, start, cur))
    return "".join(parts), page_offsets

def find_anchors(doc_text: str):
    """
    Detect anchor lines. We accept either:
      - Lines starting with '#' then 'BND...' (Markdown-like)
      - Lines starting directly with 'BND...' (PDF headings without '#')
    A line is considered an anchor if it's reasonably short and contains
    uppercase/digits and dash-like characters (hyphen '-' or dashes '–', '—').
    """
    anchors = []

    # Two regex passes: with leading '#', and without
    patterns = [
        re.compile(r"(?m)^[ \t]*#([^\n\r]{1,140})"),
        re.compile(r"(?m)^[ \t]*((?:BND)[^\n\r]{0,140})")
    ]

    for pat in patterns:
        for m in pat.finditer(doc_text):
            body = m.group(1).strip()
            body_norm = re.sub(r"\s+", " ", body)
            looks_id = bool(re.search(r"(?:\bBND\b).*([\-–—_]|[0-9]{2,}|[A-Z]{2,})", body_norm))
            if looks_id:
                anchors.append({
                    "anchor_id": body_norm,
                    "start": m.start(),
                    "end": m.end()
                })

    # Sort by start and drop exact duplicate (id,start) pairs
    anchors.sort(key=lambda a: a["start"])
    dedup = []
    seen = set()
    for a in anchors:
        key = (a["anchor_id"], a["start"])
        if key in seen: 
            continue
        seen.add(key)
        dedup.append(a)
    return dedup

def chunk_by_anchors(doc_text, anchors, page_offsets, source_name, version="v1"):
    chunks = []
    for i, a in enumerate(anchors):
        start = a["start"]
        end = anchors[i+1]["start"] if i+1 < len(anchors) else len(doc_text)
        chunk_text = doc_text[start:end].strip()

        # Page overlap estimate
        pages_in = [pg for (pg, s, e) in page_offsets if not (e <= start or s >= end)]
        page_start = pages_in[0] if pages_in else None
        page_end = pages_in[-1] if pages_in else None

        chunks.append({
            "anchor_id": a["anchor_id"],
            "text_raw": chunk_text,
            "text_norm": re.sub(r"[“”]", '"', re.sub(r"[’]", "'", chunk_text)),
            "taxonomy_refs": {"pain_point_id":"", "insight_refs":[]},
            "synonyms": [],  # optional; you will enrich from synonyms.json later
            "meta": {
                "role_level": "junior",
                "domain": "tech",
                "source_doc": source_name,
                "page_start": page_start,
                "page_end": page_end,
                "char_range": [int(start), int(end)],
                "version": version,
                "ingested_at": now_iso()
            }
        })
    return chunks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Path to your rag_project root")
    ap.add_argument("--pdf", required=False, help="Specific PDF filename in vault/ (if omitted, use allowlist in config)")
    ap.add_argument("--version", default="v1", help="Ingestion version tag (e.g., v1, v1.1)")
    args = ap.parse_args()

    base = Path(args.project).resolve()
    cfg_file = base/"configs"/"config.yml"
    if not cfg_file.exists():
        cfg_file = base/"configs"/"config.yaml"
    if not cfg_file.exists():
        print(f"ERROR: config.yml not found under {base/'configs'}", file=sys.stderr)
        sys.exit(1)
    config = load_yaml(cfg_file)

    index_dir = base/"vault_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    report_path = index_dir/"parse_report.json"
    log_path = index_dir/"parse_log.jsonl"
    chunks_path = index_dir/"chunks.jsonl"

    def log(ev):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # Determine PDFs to parse
    candidates = []
    if args.pdf:
        p = base/"vault"/args.pdf
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)
        candidates = [p]
    else:
        allowlist = (config.get("vault") or {}).get("allowlist", [])
        for name in allowlist:
            p = base/"vault"/name
            if p.exists():
                candidates.append(p)
            else:
                log({"level":"warning","msg":"allowlisted PDF missing from vault/", "file": name})

    if not candidates:
        print("ERROR: No PDFs to parse (supply --pdf or set vault.allowlist).", file=sys.stderr)
        sys.exit(1)

    all_chunks = []
    anchors_total = 0
    pages_total = 0
    for pdf in candidates:
        pages_text, backend = extract_pages_text(pdf)
        if not pages_text or not any(t for _,t in pages_text):
            log({"level":"error","msg":"Text extraction failed", "pdf": str(pdf)})
            continue
        doc_text, page_offsets = build_doc_with_page_offsets(pages_text)
        anchors = find_anchors(doc_text)
        anchors_total += len(anchors)
        pages_total += len(pages_text)
        log({"level":"info","msg":"pdf_parsed","pdf": str(pdf), "backend": backend, "pages": len(pages_text), "anchors_found": len(anchors)})
        chunks = chunk_by_anchors(doc_text, anchors, page_offsets, pdf.name, version=args.version)
        all_chunks.extend(chunks)

    # Write outputs
    if all_chunks:
        with open(chunks_path, "w", encoding="utf-8") as f:
            for ch in all_chunks:
                f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        report = {
            "status": "ok",
            "time": now_iso(),
            "pages": pages_total,
            "anchors_found": anchors_total,
            "chunks_written": len(all_chunks),
            "paths": {"chunks_jsonl": str(chunks_path), "parse_log": str(log_path)}
        }
    else:
        report = {"status": "fail", "reason": "No chunks written (no anchors or no text).", "time": now_iso()}

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print a quick summary + first few anchors
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if all_chunks:
        sample = [{"anchor_id": c["anchor_id"], "page_range": [c["meta"]["page_start"], c["meta"]["page_end"]]} for c in all_chunks[:10]]
        print("\nSample anchors:", json.dumps(sample, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
