#!/usr/bin/env python3
"""
Phase 2 — Cleaning (LOSSLESS by default)

Default behavior (--mode lossless):
  • Copies Docling Markdown to 3_clean/ WITHOUT modifying bytes.
  • Builds blocks.jsonl from the copied file, preserving line structure (no wrapping).

Optional modes (explicit):
  --mode safe       : light, semantics-preserving cleanup (NFKC, de-hyphen across linebreaks, no header/footer removal).
  --mode aggressive : safe + optional repeated-line removal + soft-wrap merge + user rules.

Inputs:
  2_docling/<DOCID>/<DOCID>_<version>.md
  (optional) 0_phase0/cleaning_rules.json  (used only in safe/aggressive)

Outputs (per DOCID):
  3_clean/<DOCID>/<DOCID>_<version>_clean.md
  3_clean/<DOCID>/<DOCID>_<version>_blocks.jsonl
  3_clean/stats.jsonl  # one line per doc

Usage (Windows CMD):
  python scripts\phase2_clean_pipeline.py
  python scripts\phase2_clean_pipeline.py --only DOC01 DOC02
  python scripts\phase2_clean_pipeline.py --mode safe --rebuild
"""
import argparse, sys, json, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime

# ---------- Parsers ----------
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
BULLET_RE  = re.compile(r'^\s*([-*+•])\s+(.*)$')
NUM_RE     = re.compile(r'^\s*(\d+)[\.\)]\s+(.*)$')
FENCE_RE   = re.compile(r'^`{3,}')
TABLE_SEP  = re.compile(r'^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$')

# ---------- Lossless helpers (no content changes) ----------
def raw_copy(src: Path, dst: Path):
    """Byte-for-byte copy of markdown (preserves CRLF/LF and all characters)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

def latest_md(doc_dir: Path):
    mds = sorted(doc_dir.glob("*.md"))
    if not mds:
        return None, None
    md = mds[-1]
    version = md.stem.split("_")[-1] if "_" in md.stem else ""
    return md, version

def read_text_preserve_newlines(p: Path) -> str:
    # Preserve end-of-line characters exactly as-is
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()

# ---------- Optional cleaning (only in safe/aggressive) ----------
def normalize_text_nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)

def dehyphenate_across_linebreaks(s: str) -> str:
    # join only when pattern is "letter - newline letter" (common PDF wrap)
    return re.sub(r'([A-Za-z])-\r?\n([a-z])', r'\1\2', s)

def remove_repeated_lines(text: str, min_occ=5, max_len=80) -> str:
    lines = text.splitlines()
    freq = {}
    for ln in lines:
        k = ln.strip()
        if 0 < len(k) <= max_len:
            freq[k] = freq.get(k,0)+1
    drop = {k for k,v in freq.items() if v >= min_occ}
    if not drop:
        return text
    return "\n".join([ln for ln in lines if ln.strip() not in drop])

def merge_soft_wraps(text: str) -> str:
    # Merge soft-wrapped paragraphs while preserving code fences/tables/headings/lists
    lines = text.splitlines()
    out, buf = [], ""
    in_fence = False

    def flush():
        nonlocal buf
        if buf:
            out.append(buf)
            buf = ""

    i = 0
    while i < len(lines):
        ln = lines[i]

        if FENCE_RE.match(ln):
            flush()
            out.append(ln)
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            out.append(ln); i += 1; continue

        if "|" in ln and (i+1 < len(lines) and TABLE_SEP.match(lines[i+1])):
            flush()
            out.append(ln); i += 1
            while i < len(lines) and lines[i].strip() != "":
                out.append(lines[i]); i += 1
            if i < len(lines) and lines[i].strip() == "":
                out.append(lines[i]); i += 1
            continue

        if HEADING_RE.match(ln) or BULLET_RE.match(ln) or NUM_RE.match(ln):
            flush(); out.append(ln); i += 1; continue

        if ln.strip() == "":
            flush(); out.append(""); i += 1; continue

        if buf == "":
            buf = ln.rstrip("\n")
        else:
            buf += " " + ln.strip()
        i += 1

    flush()
    return "\n".join(out)

def apply_user_rules(text: str, rules: dict) -> str:
    # Remove lines
    for pat in rules.get("remove_lines_matching", []):
        try:
            rx = re.compile(pat)
            text = "\n".join([ln for ln in text.splitlines() if not rx.search(ln)])
        except re.error:
            pass
    # Replace patterns
    for r in rules.get("replace", []):
        pat, repl = r.get("pattern"), r.get("repl","")
        if not pat: continue
        try:
            text = re.sub(pat, repl, text)
        except re.error:
            pass
    return text

def read_rules(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"remove_lines_matching": [], "replace": []}
    return {"remove_lines_matching": [], "replace": []}

def clean_md_by_mode(raw_md: str, mode: str, rules: dict) -> str:
    """
    lossless   : return raw_md unchanged
    safe       : NFKC + dehyphen across linebreaks ONLY
    aggressive : safe + remove_repeated_lines + merge_soft_wraps + user rules
    """
    if mode == "lossless":
        return raw_md
    s = raw_md
    if mode in ("safe", "aggressive"):
        s = normalize_text_nfkc(s)
        s = dehyphenate_across_linebreaks(s)
        if mode == "aggressive":
            s = remove_repeated_lines(s, 5, 80)
            s = merge_soft_wraps(s)
            s = apply_user_rules(s, rules)
    return s

# ---------- Block builder (preserves content lines) ----------
def build_blocks(markdown_text: str, doc_id: str, version: str):
    """
    Produce blocks while preserving internal line breaks for paragraphs
    (paragraph text is joined with '\n' instead of spaces).
    """
    blocks = []
    section_path = []
    lines = markdown_text.splitlines()

    def add(bt, text, level=None):
        blk = {
            "doc_id": doc_id,
            "version": version,
            "block_index": len(blocks),
            "block_type": bt,
            "text": text,                    # exact text (no strip)
            "section_path": section_path[:]  # copy
        }
        if level is not None:
            blk["heading_level"] = level
        blocks.append(blk)

    i = 0
    while i < len(lines):
        ln = lines[i]

        # code fence block
        if FENCE_RE.match(ln):
            fence = [ln]; i += 1
            while i < len(lines):
                fence.append(lines[i])
                if FENCE_RE.match(lines[i]):
                    i += 1; break
                i += 1
            add("code", "\n".join(fence))
            continue

        # table block
        if "|" in ln and (i+1 < len(lines) and TABLE_SEP.match(lines[i+1])):
            tbl = [ln, lines[i+1]]; i += 2
            while i < len(lines) and lines[i].strip() != "":
                tbl.append(lines[i]); i += 1
            add("table", "\n".join(tbl))
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            continue

        # heading (store full heading line as text)
        m = HEADING_RE.match(ln)
        if m:
            hashes, title = m.groups()
            level = len(hashes)
            if len(section_path) >= level:
                section_path = section_path[:level-1]
            section_path.append(title.strip())
            add("heading", ln, level)
            i += 1
            continue

        # blank lines -> passthrough? We skip creating blocks for pure blanks.
        if ln.strip() == "":
            i += 1
            continue

        # list items (store exact line minus trailing newline)
        if BULLET_RE.match(ln) or NUM_RE.match(ln):
            add("list_item", ln.rstrip("\n"))
            i += 1
            continue

        # paragraph: preserve original line breaks using '\n'
        para = [ln.rstrip("\n")]
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            # stop on structural markers
            if (nxt.strip() == "" or HEADING_RE.match(nxt) or BULLET_RE.match(nxt) or
                NUM_RE.match(nxt) or FENCE_RE.match(nxt) or
                ("|" in nxt and (j+1 < len(lines) and TABLE_SEP.match(lines[j+1])))):
                break
            para.append(nxt.rstrip("\n")); j += 1
        add("paragraph", "\n".join(para))
        i = j

    return blocks

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="Process only these DOCIDs")
    ap.add_argument("--rebuild", action="store_true", help="Rebuild even if outputs exist")
    ap.add_argument("--mode", choices=["lossless","safe","aggressive"], default="lossless",
                    help="Cleaning mode (default: lossless — NO content changes)")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    docling = base / "2_docling"
    outroot = base / "3_clean"
    outroot.mkdir(parents=True, exist_ok=True)

    rules = read_rules(base / "0_phase0" / "cleaning_rules.json")

    docs = sorted([p for p in docling.glob("DOC*") if p.is_dir()])
    if args.only:
        docs = [p for p in docs if p.name in set(args.only)]

    stats = []
    for d in docs:
        md_path, version = latest_md(d)
        if not md_path:
            print(f"[{d.name}] No markdown found. Run Phase 1 first.", file=sys.stderr)
            continue

        out_dir = outroot / d.name
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_md_path = out_dir / f"{d.name}_{version}_clean.md"
        blocks_path   = out_dir / f"{d.name}_{version}_blocks.jsonl"

        if not args.rebuild and clean_md_path.exists() and blocks_path.exists():
            print(f"[{d.name}] Skipping (already cleaned). Use --rebuild to force.")
            continue

        if args.mode == "lossless":
            # Byte-for-byte copy to preserve content exactly
            raw_copy(md_path, clean_md_path)
            md_text_for_blocks = read_text_preserve_newlines(md_path)
        else:
            raw_md = read_text_preserve_newlines(md_path)
            cleaned = clean_md_by_mode(raw_md, args.mode, rules)
            clean_md_path.write_text(cleaned, encoding="utf-8", newline="\n")
            md_text_for_blocks = cleaned

        # Build blocks without altering text
        blks = build_blocks(md_text_for_blocks, d.name, version)
        with open(blocks_path, "w", encoding="utf-8", newline="\n") as f:
            for b in blks:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")

        doc_stats = {
            "doc_id": d.name, "version": version,
            "paragraphs": sum(1 for b in blks if b["block_type"]=="paragraph"),
            "headings":   sum(1 for b in blks if b["block_type"]=="heading"),
            "list_items": sum(1 for b in blks if b["block_type"]=="list_item"),
            "tables":     sum(1 for b in blks if b["block_type"]=="table"),
            "blocks":     len(blks),
            "mode":       args.mode,
            "clean_md":   str(clean_md_path),
            "blocks_jsonl": str(blocks_path),
            "cleaned_at": datetime.utcnow().isoformat()+"Z"
        }
        stats.append(doc_stats)
        print(f"[{d.name}] mode={args.mode} → blocks={doc_stats['blocks']}")

    (outroot / "stats.jsonl").write_text("\n".join(json.dumps(s) for s in stats), encoding="utf-8")
    print("Done. Outputs in 3_clean/.")

if __name__ == "__main__":
    main()
