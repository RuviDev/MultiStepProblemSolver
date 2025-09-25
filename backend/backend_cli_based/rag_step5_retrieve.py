#!/usr/bin/env python3
"""
Step 5 — Retrieval + Evidence Pack Compression

This script loads your Step-3 hybrid index artifacts and returns an
Evidence Pack suitable for Step-6 (UAA).

Usage:
  python rag_step5_retrieve.py retrieve --project ./rag_project --q "analysis paralysis" --k 8 --threshold strict
  # Optional knobs:
  #   --bullets 4            # 3..5 recommended
  #   --max_chunk_chars 6000 # cap text length before compression

Outputs JSON to stdout with shape:
{
  "query": "...",
  "filters": {...},
  "results": [...],           # the raw top-k hits (as in Step-3 query)
  "evidence_pack": [
     {"id":"S1","anchor_id":"...","bullets":[...],
      "meta":{"source_doc":"...","page_start":...,"page_end":...,"anchor":"..."}}
  ],
  "retrieval_meta": {...}
}
"""

import argparse, json, re, sys
from pathlib import Path
from typing import List, Dict, Any
import numpy as np

try:
    import yaml
except Exception:
    yaml = None

try:
    from rank_bm25 import BM25Okapi
except Exception as e:
    print("Please install rank-bm25: pip install rank-bm25", file=sys.stderr); raise

try:
    from sentence_transformers import SentenceTransformer
except Exception as e:
    print("Please install sentence-transformers: pip install sentence-transformers", file=sys.stderr); raise

def load_yaml(p: Path):
    if yaml is None:
        return {"_raw_text": p.read_text(encoding="utf-8")}
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def tokenize(text: str) -> List[str]:
    text = text.lower()
    return re.findall(r"[a-z0-9_]+", text)

def phrase_token(phrase: str) -> str:
    return re.sub(r"\s+", "_", phrase.strip().lower())

def z_norm(a):
    a = np.array(a, dtype="float32")
    mu = a.mean(); sd = a.std() + 1e-6
    return (a - mu) / sd

def mmr(candidate_vecs: np.ndarray, query_vec: np.ndarray, k: int, lambda_: float = 0.7) -> List[int]:
    if candidate_vecs.shape[0] == 0:
        return []
    A = candidate_vecs / (np.linalg.norm(candidate_vecs, axis=1, keepdims=True) + 1e-9)
    q = query_vec / (np.linalg.norm(q_vec := query_vec) + 1e-9)
    sim_to_q = A @ q  # [N]
    selected = []
    remaining = list(range(len(sim_to_q)))
    while remaining and len(selected) < k:
        if selected:
            sel_vecs = A[selected]
            max_sim_sel = np.max(A[remaining] @ sel_vecs.T, axis=1)
        else:
            max_sim_sel = np.zeros(len(remaining))
        scores = lambda_ * sim_to_q[remaining] - (1.0 - lambda_) * max_sim_sel
        best_idx = remaining[int(np.argmax(scores))]
        selected.append(best_idx)
        remaining.remove(best_idx)
    return selected

def extract_inline_synonyms(text_raw: str) -> List[str]:
    syns = []
    m = re.search(r"(?i)(keywords\s*/\s*synonyms)\s*:\s*([\s\S]{0,400})", text_raw)
    if m:
        tail = m.group(2).splitlines()[:2]
        tail = " ".join(tail)
        items = [s.strip(" .,:;") for s in re.split(r"[;,]", tail) if s.strip()]
        syns = list(dict.fromkeys(items))
    return syns

def load_chunks_map(chunks_path: Path) -> Dict[str, Dict[str, Any]]:
    m = {}
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            aid = obj.get("anchor_id")
            if not aid: 
                continue
            # Keep the first occurrence; if duplicates exist, we keep the earliest
            if aid not in m:
                m[aid] = obj
    return m

def sentence_split(text: str) -> List[str]:
    # Simple sentence splitter: keeps bullets as separate "sentences"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sent = []
    for ln in lines:
        if re.match(r"^(\u2022|•|-|->|\*)\s+", ln):
            sent.append(ln)
        else:
            # split into sentences
            parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9\"\'(•\-\*])', ln)
            for p in parts:
                p = p.strip()
                if p: sent.append(p)
    # de-dup while preserving order
    seen=set(); out=[]
    for s in sent:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def score_sentences(sents: List[str], query: str, syns: List[str]) -> List[float]:
    # Scoring heuristic: token overlap with query + phrase matches for synonyms + bullet bonus
    q_tokens = set(tokenize(query))
    syn_phr = [s.lower() for s in syns]
    scores = []
    for s in sents:
        s_low = s.lower()
        toks = set(tokenize(s_low))
        base = len(q_tokens & toks)
        phrase_hits = sum(1 for phr in syn_phr if phr and phr in s_low)
        bullet_bonus = 1 if re.match(r"^(\u2022|•|-|->|\*)\s+", s.strip()) else 0
        scores.append(base + 1.5*phrase_hits + 0.5*bullet_bonus)
    return scores

def compress_chunk(text_raw: str, query: str, syns: List[str], bullets: int = 4, max_chars: int = 160) -> List[str]:
    sents = sentence_split(text_raw)
    if not sents:
        return []
    scores = score_sentences(sents, query, syns)
    ranked = [s for _, s in sorted(zip(scores, sents), key=lambda x: -x[0])]
    out = []
    seen_substr = set()
    for s in ranked:
        # Clean/trim
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > max_chars:
            s = s[:max_chars-1] + "…"
        key = s.lower()
        # Avoid near-duplicates by substring check
        if any(key in prev or prev in key for prev in seen_substr):
            continue
        seen_substr.add(key)
        out.append(("• " + s) if not s.startswith(("•","-","->","*")) else s)
        if len(out) >= bullets:
            break
    # If still short, backfill from the top sentences
    i = 0
    while len(out) < bullets and i < len(sents):
        s = sents[i].strip()
        s = re.sub(r"\s+", " ", s)
        if s and s.lower() not in seen_substr:
            out.append(("• " + s) if not s.startswith(("•","-","->","*")) else s)
        i += 1
    return out[:bullets]

def retrieve(project: Path, q: str, k: int, threshold_mode: str, bullets: int, max_chunk_chars: int):
    # Load config and artifacts
    cfg_file = project/"configs"/"config.yml"
    if not cfg_file.exists():
        cfg_file = project/"configs"/"config.yaml"
    config = load_yaml(cfg_file)
    thresholds = config.get("thresholds") or {}
    strict = float(thresholds.get("strict", 0.35))
    lenient = float(thresholds.get("lenient", 0.25))
    thr = strict if threshold_mode == "strict" else lenient

    retrieval_cfg = config.get("retrieval") or {}
    mmr_lambda = float(retrieval_cfg.get("mmr_lambda", 0.7))

    index_dir = project/"vault_index"
    id_map = json.loads((index_dir/"id_map.json").read_text(encoding="utf-8"))
    bm25_docs = json.loads((index_dir/"bm25_corpus.json").read_text(encoding="utf-8"))
    meta_map = json.loads((index_dir/"meta.json").read_text(encoding="utf-8"))
    manifest = json.loads((index_dir/"manifest.json").read_text(encoding="utf-8"))

    # Build BM25 object
    bm25 = BM25Okapi(bm25_docs)

    # Load embeddings / FAISS
    emb_model_name = (config.get("models") or {}).get("embedding", "all-MiniLM-L6-v2")
    emb_model = SentenceTransformer(emb_model_name)
    have_faiss = (index_dir/"faiss.index").exists()

    q_tokens = tokenize(q) + [phrase_token(q)]
    bm25_scores = bm25.get_scores(q_tokens)

    if have_faiss:
        try:
            import faiss
        except Exception:
            raise RuntimeError("faiss.index present but faiss not installed. Install faiss-cpu or rebuild without FAISS.")
        index = faiss.read_index(str(index_dir/"faiss.index"))
        q_vec = emb_model.encode([q], convert_to_numpy=True)[0].astype("float32")
        q_vec /= (np.linalg.norm(q_vec) + 1e-9)
        sims, idxs = index.search(q_vec.reshape(1,-1), max(50, k*5))
        idxs = idxs[0]; sims = sims[0]
        emb_scores = np.zeros(len(id_map), dtype="float32")
        for i, ix in enumerate(idxs):
            if ix >= 0:
                emb_scores[ix] = sims[i]
        X = None
    else:
        X = np.load(index_dir/"dense.npy")
        q_vec = emb_model.encode([q], convert_to_numpy=True)[0].astype("float32")
        norms = np.linalg.norm(X, axis=1) * (np.linalg.norm(q_vec) + 1e-9)
        emb_scores = (X @ q_vec) / (norms + 1e-9)

    s_bm25 = z_norm(bm25_scores)
    s_emb = z_norm(emb_scores)
    combo = 0.5*s_bm25 + 0.5*s_emb

    topN = int(max(12, k*2))
    idx_sorted = list(np.argsort(-combo)[:topN])
    if X is None:
        selected = idx_sorted[:k]
    else:
        sel_local = mmr(X[idx_sorted], q_vec, k=k, lambda_=mmr_lambda)
        selected = [idx_sorted[i] for i in sel_local]

    if not selected or float(combo[selected[0]]) < thr:
        out = {
            "query": q,
            "filters": config.get("filters", {}),
            "results": [],
            "evidence_pack": [],
            "retrieval_meta": {
                "k": k,
                "pipeline": ["bm25","embed","mmr"],
                "embedding_model": emb_model_name,
                "threshold": threshold_mode,
                "note": f"no result above threshold ({thr})"
            }
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    # Build raw results
    # Load text_store for quick snippets
    text_store = {}
    with open(index_dir/"text_store.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            text_store[obj["anchor_id"]] = obj["snippet"]

    raw_results = []
    selected = selected[:k]
    for ix in selected:
        aid = id_map[ix]
        m = meta_map.get(aid, {})
        raw_results.append({
            "anchor_id": aid,
            "score": float(combo[ix]),
            "snippet": (text_store.get(aid, "")[:200].replace("\n"," ")),
            "source_doc": m.get("source_doc"),
            "page": m.get("page_start")
        })

    # Compression: need full chunk text + synonyms (both curated and inline)
    chunks_map = load_chunks_map(index_dir/"chunks.jsonl")
    syn_path = project/"configs"/"synonyms.json"
    synonyms = {}
    if syn_path.exists():
        try:
            synonyms = json.loads(syn_path.read_text(encoding="utf-8"))
        except Exception:
            synonyms = {}

    pack = []
    for i, ix in enumerate(selected, start=1):
        aid = id_map[ix]
        ch = chunks_map.get(aid, {})
        full_text = ch.get("text_raw", "")
        if max_chunk_chars and len(full_text) > max_chunk_chars:
            full_text = full_text[:max_chunk_chars]
        # Collect synonyms for scoring
        syns = []
        if isinstance(synonyms.get(aid, {}), dict):
            syns.extend(synonyms[aid].get("synonyms", []))
        syns.extend(extract_inline_synonyms(full_text))
        # Compress
        bullet_lines = compress_chunk(full_text, q, syns, bullets=bullets)
        meta = ch.get("meta", {}).copy() if isinstance(ch.get("meta"), dict) else {}
        meta["anchor"] = aid
        pack.append({
            "id": f"S{i}",
            "anchor_id": aid,
            "bullets": bullet_lines,
            "meta": {
                "source_doc": meta.get("source_doc"),
                "page_start": meta.get("page_start"),
                "page_end": meta.get("page_end"),
                "anchor": aid
            }
        })

    out = {
        "query": q,
        "filters": config.get("filters", {}),
        "results": raw_results,
        "evidence_pack": pack,
        "retrieval_meta": {
            "k": k,
            "pipeline": ["bm25","embed","mmr","compress"],
            "embedding_model": emb_model_name,
            "threshold": threshold_mode
        }
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("retrieve", help="Retrieve and compress into an Evidence Pack")
    r.add_argument("--project", required=True, help="Path to rag_project")
    r.add_argument("--q", required=True, help="User query")
    r.add_argument("--k", type=int, default=8, help="How many chunks to include (default 8)")
    r.add_argument("--threshold", choices=["strict","lenient"], default="strict")
    r.add_argument("--bullets", type=int, default=4, help="Bullets per chunk (3–5 recommended)")
    r.add_argument("--max_chunk_chars", type=int, default=6000, help="Cap raw text length before compression")

    args = ap.parse_args()
    project = Path(args.project).resolve()

    if args.cmd == "retrieve":
        retrieve(project, args.q, args.k, args.threshold, args.bullets, args.max_chunk_chars)

if __name__ == "__main__":
    main()
