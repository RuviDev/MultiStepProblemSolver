#!/usr/bin/env python3
"""
Phase 4 — Query hybrid index (FAISS + BM25) with Reciprocal Rank Fusion (RRF)

Usage (Windows CMD):
  python scripts\phase4_query.py --q "what is UVA?" --top 8
  python scripts\phase4_query.py --q "batch 3 insights" --top 10 --doc DOC02
"""
import sys, json, re, pickle, argparse
from pathlib import Path
from typing import List, Tuple, Dict
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

try:
    import faiss
except Exception:
    print("ERROR: faiss not installed. pip install faiss-cpu", file=sys.stderr)
    sys.exit(1)

BASE = Path(__file__).resolve().parents[1]
IDX  = BASE / "5_index"
CHUNKS = BASE / "4_chunks"

@dataclass
class Meta:
    chunk_id: str
    doc_id: str
    version: str
    section_path: list
    breadcrumb: str
    section_group_id: str
    chunk_type: str
    token_count: int

def load_meta(path: Path) -> List[Meta]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append(Meta(
                chunk_id=r["chunk_id"],
                doc_id=r["doc_id"],
                version=r.get("version",""),
                section_path=r.get("section_path",[]),
                breadcrumb=r.get("breadcrumb",""),
                section_group_id=r.get("section_group_id",""),
                chunk_type=r.get("chunk_type","text"),
                token_count=r.get("token_count",0),
            ))
    return rows

def tokenize(s: str):
    return re.findall(r"[A-Za-z0-9_]+", s.lower())

def rrf_fuse(ranklists: Dict[str, Dict[str,int]], k: int = 60) -> Dict[str, float]:
    """
    ranklists: { 'bm25': {chunk_id: rank}, 'vec': {chunk_id: rank}, ... }
    Returns combined RRF scores per chunk_id
    """
    scores = {}
    for source, ranks in ranklists.items():
        for cid, r in ranks.items():
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
    return scores

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True, help="query text")
    ap.add_argument("--top", type=int, default=8, help="top-N to print")
    ap.add_argument("--kvec", type=int, default=50, help="vector top-K before fusion")
    ap.add_argument("--klex", type=int, default=50, help="BM25 top-K before fusion")
    ap.add_argument("--doc", type=str, default=None, help="optional filter: DOCID (e.g., DOC03)")
    args = ap.parse_args()

    # load indexes
    meta = load_meta(IDX / "meta.jsonl")
    chunkid_to_idx = {m.chunk_id: i for i, m in enumerate(meta)}

    with open(IDX / "bm25.pkl", "rb") as f:
        bm25: BM25Okapi = pickle.load(f)
    bm25_doc_ids = json.loads((IDX / "bm25_doc_ids.json").read_text(encoding="utf-8"))

    cfg = json.loads((IDX / "index_config.json").read_text(encoding="utf-8"))
    model = SentenceTransformer(cfg["model_name"])
    index = faiss.read_index(str(IDX / "vector.faiss"))

    # optional filter set
    allowed_ids = None
    if args.doc:
        allowed_ids = {m.chunk_id for m in meta if m.doc_id == args.doc}

    # --- vector search ---
    qvec = model.encode([args.q], normalize_embeddings=True).astype("float32")
    sims, idxs = index.search(qvec, args.kvec)
    idxs = idxs[0].tolist()
    sims = sims[0].tolist()

    vec_pairs = []
    for pos, (i, s) in enumerate(zip(idxs, sims), start=1):
        if i < 0: continue
        cid = meta[i].chunk_id
        if allowed_ids and cid not in allowed_ids: 
            continue
        vec_pairs.append((cid, pos))  # keep rank only for RRF

    # --- BM25 ---
    toks = tokenize(args.q)
    scores = bm25.get_scores(toks)
    # get top indices
    top_idx = np.argsort(scores)[::-1][:args.klex]
    bm25_pairs = []
    for pos, i in enumerate(top_idx, start=1):
        cid = bm25_doc_ids[i]
        if allowed_ids and cid not in allowed_ids:
            continue
        bm25_pairs.append((cid, pos))

    # --- RRF fusion ---
    ranklists = {
        "bm25": {cid: rank for cid, rank in bm25_pairs},
        "vec":  {cid: rank for cid, rank in vec_pairs},
    }
    fused = rrf_fuse(ranklists, k=60)
    # sort by score desc
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:args.top]

    # load chunk texts for display (stream from files)
    # quick map from chunk_id -> (doc_dir, version) so we can open right file
    # Since text is inside the chunks jsonl, easiest is: scan the doc's chunks file when needed
    # Build per-doc cache
    chunk_cache = {}  # chunk_id -> record

    def load_chunk_record(chunk_id: str):
        if chunk_id in chunk_cache:
            return chunk_cache[chunk_id]
        # parse doc_id from cid prefix
        doc_id = chunk_id.split(":")[0]
        # open the latest chunks file under that doc
        paths = sorted((BASE / "4_chunks" / doc_id).glob("*_chunks.jsonl"))
        if not paths:
            return None
        # scan (could be optimized)
        with paths[-1].open("r", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("chunk_id") == chunk_id:
                    chunk_cache[chunk_id] = r
                    return r
        return None

    # Pretty print
    from rich.console import Console
    from rich.markdown import Markdown
    console = Console()

    console.rule("[bold]Hybrid results (RRF)")
    for rank, (cid, score) in enumerate(ranked, start=1):
        m = meta[chunkid_to_idx[cid]]
        r = load_chunk_record(cid)
        if not r: 
            continue
        snippet = r["text"]
        snippet = snippet.strip().replace("\r","")
        if len(snippet) > 600:
            snippet = snippet[:600] + " …"

        header = f"[{rank}] {m.doc_id} | {m.breadcrumb or '∅'} | chunk_id={cid} | score={score:.4f}"
        console.print(f"[bold]{header}[/bold]")
        console.print(Markdown(snippet))
        console.print("-" * 80)

if __name__ == "__main__":
    main()
