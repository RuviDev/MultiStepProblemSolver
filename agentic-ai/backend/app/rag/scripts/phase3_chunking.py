#!/usr/bin/env python3
r"""
Phase 3 — Chunking (content-preserving, section-aware, breadcrumb embeddings)

Reads Phase-02 outputs (3_clean/DOCxx/*_blocks.jsonl) and groups blocks into
retrieval chunks within a token budget. It never edits block text; it only concatenates
whole content blocks (paragraphs/list items) with "\n\n". Tables and code blocks are
kept atomic (stand-alone chunks). Headings are NOT injected into visible text unless
you set include_headings_in_text=true, but they are used for boundaries + breadcrumbs.

Outputs (per DOCID):
  4_chunks/<DOCID>/<DOCID>_<version>_chunks.jsonl   # one JSON per chunk
  4_chunks/stats.jsonl                              # one line per doc with counts

CLI (Windows CMD examples):
  python scripts\phase3_chunking.py
  python scripts\phase3_chunking.py --only DOC01 DOC02
  python scripts\phase3_chunking.py --rebuild
  python scripts\phase3_chunking.py --target 900 --max 1200 --min 150 --overlap 80
"""

import argparse, sys, json, re, os, hashlib
from pathlib import Path
from datetime import datetime

# ---------- tokenization ----------
def _get_token_fn():
    """Prefer tiktoken (accurate). Fallback to a regex tokenizer."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return lambda s: len(enc.encode(s))
    except Exception:
        tokre = re.compile(r"\w+|[^\w\s]", re.UNICODE)
        return lambda s: len(tokre.findall(s))

count_tokens = _get_token_fn()

# ---------- utils ----------
def latest_file(dirpath: Path, suffix: str):
    cand = sorted(dirpath.glob(f"*{suffix}"))
    return cand[-1] if cand else None

def read_blocks_jsonl(path: Path):
    blocks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                blocks.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return blocks

def chunk_id(doc_id: str, version: str, idx: int, start_bi: int, end_bi: int, text: str):
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}:{version}:{start_bi}-{end_bi}:{idx:04d}:{h}"

def choose_section_path(blocks):
    # Deepest path from first non-heading block
    for b in blocks:
        if b["block_type"] != "heading":
            return b.get("section_path", [])
    return (blocks[0].get("section_path", []) if blocks else [])

def breadcrumb_from(sp, depth=2, joiner=" > "):
    if not sp:
        return ""
    return joiner.join(sp[-depth:])

# ---------- chunker ----------
def build_chunks(blocks, cfg):
    tgt  = int(cfg.get("target_tokens", 800))
    mx   = int(cfg.get("max_tokens", 1100))
    mn   = int(cfg.get("min_tokens", 150))
    ovlp = int(cfg.get("overlap_tokens", 80))
    incl_headings = bool(cfg.get("include_headings_in_text", False))
    break_on_level = int(cfg.get("break_on_heading_level", 0))

    chunks = []
    buf_blocks = []
    buf_text = ""
    buf_tokens = 0
    buf_start_idx = None

    def flush_chunk():
        nonlocal buf_blocks, buf_text, buf_tokens, buf_start_idx
        if not buf_blocks:
            return None
        start_bi = buf_start_idx
        end_bi   = buf_blocks[-1]["block_index"]
        ch = {
            "_blocks": [b["block_index"] for b in buf_blocks],  # traceability
            "block_start_index": start_bi,
            "block_end_index": end_bi,
            "text": buf_text,
            "token_count": buf_tokens,
            "section_path": choose_section_path(buf_blocks),
            "contains_table": any(b["block_type"]=="table" for b in buf_blocks),
            "contains_code":  any(b["block_type"]=="code"  for b in buf_blocks),
            "chunk_type": "table" if len(buf_blocks)==1 and buf_blocks[0]["block_type"]=="table" else (
                          "code" if len(buf_blocks)==1 and buf_blocks[0]["block_type"]=="code" else "text")
        }
        chunks.append(ch)
        buf_blocks, buf_text, buf_tokens, buf_start_idx = [], "", 0, None
        return ch

    def add_content_block(b):
        nonlocal buf_blocks, buf_text, buf_tokens, buf_start_idx
        # tables/code are atomic
        if b["block_type"] in ("table","code"):
            flush_chunk()
            txt = b["text"]
            tokens = count_tokens(txt)
            chunks.append({
                "_blocks": [b["block_index"]],
                "block_start_index": b["block_index"],
                "block_end_index": b["block_index"],
                "text": txt,
                "token_count": tokens,
                "section_path": b.get("section_path", []),
                "contains_table": (b["block_type"]=="table"),
                "contains_code":  (b["block_type"]=="code"),
                "chunk_type": b["block_type"]
            })
            return

        # paragraph/list_item
        candidate = (buf_text + ("\n\n" if buf_text else "") + b["text"]).rstrip()
        cand_tokens = count_tokens(candidate)
        if buf_start_idx is None:
            buf_start_idx = b["block_index"]

        # if too big, flush if current buffer is healthy
        if buf_blocks and cand_tokens > mx and buf_tokens >= mn:
            flush_chunk()
            buf_blocks = [b]
            buf_text   = b["text"]
            buf_tokens = count_tokens(buf_text)
            buf_start_idx = b["block_index"]
        else:
            buf_blocks.append(b)
            buf_text = candidate
            buf_tokens = cand_tokens

        # if we reached target, flush (allowing a little slack)
        if buf_tokens >= tgt:
            flush_chunk()

    # iterate blocks with heading-aware boundaries
    for b in blocks:
        bt = b["block_type"]

        if bt == "heading":
            level = int(b.get("heading_level", 999))
            # hard boundary on new major section
            if break_on_level and level <= break_on_level:
                flush_chunk()

            # optionally include headings into visible text (usually False)
            if incl_headings:
                add_content_block(b)  # treat like content (rare)
            # even if not included, headings influence section_path which is carried in later blocks
            continue

        # normal content
        add_content_block(b)

    flush_chunk()

    # token-overlap between consecutive text chunks (doesn't mutate originals)
    if ovlp > 0 and len(chunks) > 1:
        for i in range(1, len(chunks)):
            if chunks[i]["chunk_type"] != "text":
                continue
            prev_text = chunks[i-1]["text"]
            this_text = chunks[i]["text"]
            # simple word-based overlap (cheap + safe)
            prev_words = prev_text.split()
            if len(prev_words) > ovlp:
                prefix = " ".join(prev_words[-ovlp:])
                if not this_text.startswith(prefix):
                    chunks[i]["text"] = prefix + "\n\n" + this_text
                    chunks[i]["token_count"] = count_tokens(chunks[i]["text"])
                    chunks[i]["overlap_with_prev"] = ovlp

    return chunks

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="Process only these DOCIDs")
    ap.add_argument("--rebuild", action="store_true", help="Rebuild even if outputs exist")
    ap.add_argument("--target", type=int, default=None, help="Override target_tokens")
    ap.add_argument("--max",    type=int, default=None, help="Override max_tokens")
    ap.add_argument("--min",    type=int, default=None, help="Override min_tokens")
    ap.add_argument("--overlap",type=int, default=None, help="Override overlap_tokens")
    ap.add_argument("--include-headings", action="store_true", help="Include headings inside visible chunk text")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    clean_root  = base / "3_clean"
    out_root    = base / "4_chunks"
    cfg_path    = base / "0_phase0" / "chunking_config.json"
    out_root.mkdir(parents=True, exist_ok=True)

    # defaults
    cfg = {
        "target_tokens": 800,
        "max_tokens": 1100,
        "min_tokens": 150,
        "overlap_tokens": 80,
        "include_headings_in_text": False,
        "embed_with_breadcrumbs": True,
        "breadcrumb_depth": 2,
        "breadcrumb_joiner": " > ",
        "break_on_heading_level": 2
    }
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    # CLI overrides
    if args.target  is not None: cfg["target_tokens"] = args.target
    if args.max     is not None: cfg["max_tokens"]    = args.max
    if args.min     is not None: cfg["min_tokens"]    = args.min
    if args.overlap is not None: cfg["overlap_tokens"]= args.overlap
    if args.include_headings:    cfg["include_headings_in_text"] = True

    # gather docs
    doc_dirs = sorted([p for p in clean_root.glob("DOC*") if p.is_dir()])
    if args.only:
        doc_dirs = [p for p in doc_dirs if p.name in set(args.only)]

    stats = []
    for d in doc_dirs:
        blocks_path = latest_file(d, "_blocks.jsonl")
        clean_md    = latest_file(d, "_clean.md")
        if not blocks_path or not clean_md:
            print(f"[{d.name}] Missing Phase-02 outputs. Run Phase 2 first.", file=sys.stderr)
            continue

        # infer version from filename: DOC01_20251014_blocks.jsonl
        stem = blocks_path.stem
        parts = stem.split("_")
        version = parts[1] if len(parts) >= 2 else ""

        out_dir = out_root / d.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_chunks = out_dir / f"{d.name}_{version}_chunks.jsonl"

        if out_chunks.exists() and not args.rebuild:
            print(f"[{d.name}] Skipping (already chunked). Use --rebuild to force.")
            continue

        blocks = read_blocks_jsonl(blocks_path)
        chunks = build_chunks(blocks, cfg)

        # finalize each chunk
        final = []
        for i, ch in enumerate(chunks):
            text = ch["text"]
            sp = ch["section_path"]
            bc = breadcrumb_from(sp, cfg["breadcrumb_depth"], cfg["breadcrumb_joiner"])

            # Text used for embeddings (breadcrumbs only affect *embedding*, not visible text)
            embedding_text = f"{bc}\n\n{text}" if (cfg["embed_with_breadcrumbs"] and bc) else text

            section_key = "|".join(sp) if sp else ""

            chunk_meta = {
                "chunk_id": chunk_id(d.name, version, i, ch["block_start_index"], ch["block_end_index"], text),
                "doc_id": d.name,
                "version": version,
                "chunk_index": i,
                "block_start_index": ch["block_start_index"],
                "block_end_index": ch["block_end_index"],
                "text": text,                                   # clean, visible text
                "embedding_text": embedding_text,               # for embedding/indexing
                "token_count": ch["token_count"],
                "embedding_token_count": count_tokens(embedding_text),
                "section_path": sp,
                "breadcrumb": bc,
                "section_group_id": section_key,                # helps fetch neighbor chunks in same section
                "chunk_type": ch["chunk_type"],
                "contains_table": ch["contains_table"],
                "contains_code": ch["contains_code"],
                "created_at": datetime.utcnow().isoformat() + "Z",
                "config": {
                    "target_tokens": cfg["target_tokens"],
                    "max_tokens": cfg["max_tokens"],
                    "min_tokens": cfg["min_tokens"],
                    "overlap_tokens": cfg["overlap_tokens"],
                    "include_headings_in_text": cfg["include_headings_in_text"],
                    "embed_with_breadcrumbs": cfg["embed_with_breadcrumbs"],
                    "breadcrumb_depth": cfg["breadcrumb_depth"],
                    "breadcrumb_joiner": cfg["breadcrumb_joiner"],
                    "break_on_heading_level": cfg["break_on_heading_level"]
                }
            }
            if "overlap_with_prev" in ch:
                chunk_meta["overlap_with_prev"] = ch["overlap_with_prev"]
            final.append(chunk_meta)

        with open(out_chunks, "w", encoding="utf-8") as f:
            for row in final:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        # stats
        doc_stats = {
            "doc_id": d.name,
            "version": version,
            "chunks": len(final),
            "avg_tokens": round(sum(c["token_count"] for c in final) / max(1, len(final)), 1),
            "tables": sum(1 for c in final if c["chunk_type"]=="table"),
            "codes":  sum(1 for c in final if c["chunk_type"]=="code"),
            "text_chunks": sum(1 for c in final if c["chunk_type"]=="text"),
        }
        stats.append(doc_stats)
        print(f"[{d.name}] chunks={doc_stats['chunks']} avg_tokens={doc_stats['avg_tokens']}")

    # write/overwrite overall stats
    (out_root / "stats.jsonl").write_text("\n".join(json.dumps(s) for s in stats), encoding="utf-8")
    print("Done. Outputs in 4_chunks/.")

if __name__ == "__main__":
    main()
