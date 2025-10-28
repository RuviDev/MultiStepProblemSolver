#!/usr/bin/env python3
"""
Phase 4 — Build hybrid index (vector FAISS + BM25)

Inputs:
  4_chunks/DOCxx/*_chunks.jsonl  (from Phase 03)

Outputs:
  5_index/
    vector.faiss                ← FAISS index (inner product, vectors L2-normalized)
    meta.jsonl                  ← one JSON per row in FAISS with chunk metadata
    bm25.pkl                    ← rank_bm25 BM25Okapi object
    bm25_doc_ids.json           ← list[str] mapping bm25 corpus index → chunk_id
    index_config.json           ← model + settings
    stats.json                  ← sizes, counts
"""
import os, sys, json, re, pickle, hashlib
from pathlib import Path
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

try:
    import faiss  # faiss-cpu import name is still "faiss"
except Exception as e:
    print("ERROR: faiss not installed. Install with: pip install faiss-cpu", file=sys.stderr)
    raise

# -------------------- config --------------------
BASE = Path(__file__).resolve().parents[1]
CHUNKS_ROOT = BASE / "4_chunks"
OUT_ROOT    = BASE / "5_index"
OUT_ROOT.mkdir(parents=True, exist_ok=True)

MODEL_NAME = os.environ.get("RAG_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
BATCH_SIZE = int(os.environ.get("RAG_EMBED_BATCH", "128"))
USE_EMBEDDING_TEXT = True  # use chunk["embedding_text"] if present; else fallback to chunk["text"]

# -------------------- io helpers --------------------
def load_all_chunks(chunks_root: Path):
    files = sorted(chunks_root.glob("DOC*/*_chunks.jsonl"))
    if not files:
        print("No chunk files found in 4_chunks/. Run Phase 03 first.", file=sys.stderr)
        sys.exit(1)

    rows = []
    for fp in files:
        with fp.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # guarantee fields
                row["section_path"] = row.get("section_path", [])
                row["breadcrumb"]   = row.get("breadcrumb", "")
                row["section_group_id"] = row.get("section_group_id", "|".join(row["section_path"]) if row["section_path"] else "")
                rows.append(row)
    return rows

def tokenize_for_bm25(text: str):
    # simple, robust tokenizer
    return re.findall(r"[A-Za-z0-9_]+", text.lower())

# -------------------- main build --------------------
def main():
    print("Loading chunks...")
    rows = load_all_chunks(CHUNKS_ROOT)
    print(f"  loaded {len(rows)} chunks")

    # choose field to embed and to index by BM25
    embed_texts = [(r.get("embedding_text") if USE_EMBEDDING_TEXT and r.get("embedding_text") else r["text"]) for r in rows]
    bm25_texts  = embed_texts  # breadcrumbs help lexical too

    # --- embeddings ---
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    print(f"  embedding dim = {dim}")

    vecs = []
    for i in range(0, len(embed_texts), BATCH_SIZE):
        batch = embed_texts[i:i+BATCH_SIZE]
        emb = model.encode(batch, show_progress_bar=True, normalize_embeddings=True)  # cosine via inner product
        vecs.append(emb.astype("float32"))
    vecs = np.vstack(vecs)  # shape (N, dim)

    # sanity
    assert vecs.shape[0] == len(rows), "vector count ≠ rows"

    # FAISS index (IP with normalized vectors == cosine similarity)
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)
    faiss.write_index(index, str(OUT_ROOT / "vector.faiss"))

    # persist meta in SAME ORDER as added to FAISS
    meta_path = OUT_ROOT / "meta.jsonl"
    with meta_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "version": r.get("version",""),
                "section_path": r["section_path"],
                "breadcrumb": r.get("breadcrumb",""),
                "section_group_id": r.get("section_group_id",""),
                "chunk_type": r.get("chunk_type","text"),
                "token_count": r.get("token_count", 0)
            }, ensure_ascii=False) + "\n")

    # BM25
    print("Building BM25...")
    tokenized = [tokenize_for_bm25(t) for t in bm25_texts]
    bm25 = BM25Okapi(tokenized)
    with open(OUT_ROOT / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)
    with open(OUT_ROOT / "bm25_doc_ids.json", "w", encoding="utf-8") as f:
        json.dump([r["chunk_id"] for r in rows], f)

    # config + stats
    cfg = {
        "model_name": MODEL_NAME,
        "batch_size": BATCH_SIZE,
        "vec_dim": dim,
        "normalize_vectors": True,
        "use_embedding_text": USE_EMBEDDING_TEXT,
        "built_at": datetime.utcnow().isoformat()+"Z"
    }
    (OUT_ROOT / "index_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    stats = {
        "chunks": len(rows),
        "vec_dim": dim,
        "faiss_index": "vector.faiss",
        "bm25": "bm25.pkl",
        "meta": "meta.jsonl"
    }
    (OUT_ROOT / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print("Done. Index written to 5_index/")

if __name__ == "__main__":
    main()
