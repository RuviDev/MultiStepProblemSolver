#!/usr/bin/env python3
"""
Step 3: Build a hybrid index (BM25 + embeddings) and a simple query CLI.

Usage:
  # Build indexes from chunks + synonyms
  python build_index.py build --project ./rag_project

  # Quick test query
  python build_index.py query --project ./rag_project --q "how to fix analysis paralysis" --k 8 --threshold strict

Requirements (install locally):
  pip install rank-bm25 sentence-transformers faiss-cpu numpy pyyaml
"""

import argparse, re, json, os, sys, math, datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

try:
    import yaml
except Exception:
    yaml = None

import numpy as np

# Optional libs
try:
    import faiss  # faiss-cpu
    HAVE_FAISS = True
except Exception:
    HAVE_FAISS = False

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

def now_iso():
    import datetime as _dt
    return _dt.datetime.utcnow().isoformat()+"Z"

def load_yaml(p: Path):
    if yaml is None:
        return {"_raw_text": p.read_text(encoding="utf-8")}
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def sent_tokenize(text: str) -> List[str]:
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9\"\'(])', text.strip())
    return [s.strip() for s in parts if s.strip()]

def tokenize(text: str) -> List[str]:
    text = text.lower()
    return re.findall(r"[a-z0-9_]+", text)

def phrase_token(phrase: str) -> str:
    return re.sub(r"\s+", "_", phrase.strip().lower())

def mmr(candidate_vecs: np.ndarray, query_vec: np.ndarray, k: int, lambda_: float = 0.7) -> List[int]:
    if candidate_vecs.shape[0] == 0:
        return []
    A = candidate_vecs / (np.linalg.norm(candidate_vecs, axis=1, keepdims=True) + 1e-9)
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
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

def build(project: Path):
    cfg_file = project/"configs"/"config.yml"
    if not cfg_file.exists():
        cfg_file = project/"configs"/"config.yaml"
    if not cfg_file.exists():
        print(f"ERROR: config.yml not found under {project/'configs'}", file=sys.stderr)
        sys.exit(1)
    config = load_yaml(cfg_file)

    index_dir = project/"vault_index"
    chunks_path = index_dir/"chunks.jsonl"
    syn_path = project/"configs"/"synonyms.json"
    manifest_path = index_dir/"manifest.json"
    id_map_path = index_dir/"id_map.json"
    meta_path = index_dir/"meta.json"
    text_store_path = index_dir/"text_store.jsonl"
    bm25_corpus_path = index_dir/"bm25_corpus.json"
    emb_path = index_dir/"dense.npy"
    faiss_index_path = index_dir/"faiss.index"

    if not chunks_path.exists():
        print(f"ERROR: {chunks_path} not found. Run Step-2 first.", file=sys.stderr)
        sys.exit(1)
    if not syn_path.exists():
        print(f"ERROR: {syn_path} not found. Fill synonyms before building.", file=sys.stderr)
        sys.exit(1)

    chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                chunks.append(json.loads(line))
            except Exception:
                pass
    synonyms = json.loads(Path(syn_path).read_text(encoding="utf-8"))

    emb_model_name = (config.get("models") or {}).get("embedding", "all-MiniLM-L6-v2")
    reranker_name = (config.get("models") or {}).get("reranker", None)
    retrieval_cfg = config.get("retrieval") or {}
    mmr_lambda = float(retrieval_cfg.get("mmr_lambda", 0.7))
    filters = config.get("filters") or {"role_level": "junior", "domain": "tech"}

    print(f"[build] Loading embedding model: {emb_model_name}")
    model = SentenceTransformer(emb_model_name)

    docs = []
    bm25_docs = []
    id_map = []
    meta_map = {}
    text_lines = []
    srctext_map = {}

    def include_chunk(ch: Dict[str, Any]) -> bool:
        m = ch.get("meta", {})
        if filters.get("role_level") and m.get("role_level") != filters["role_level"]:
            return False
        if filters.get("domain") and m.get("domain") != filters["domain"]:
            return False
        aid = ch.get("anchor_id","")
        if not aid.startswith(("BND", "#BND")):
            return False
        if len(ch.get("text_raw","")) < 200:
            return False
        return True

    def extract_inline_synonyms(text_raw: str) -> List[str]:
        syns = []
        m = re.search(r"(?i)(keywords\s*/\s*synonyms)\s*:\s*([\s\S]{0,400})", text_raw)
        if m:
            tail = m.group(2).splitlines()[:2]
            tail = " ".join(tail)
            items = [s.strip(" .,:;") for s in re.split(r"[;,]", tail) if s.strip()]
            syns = list(dict.fromkeys(items))
        return syns

    for ch in chunks:
        if not include_chunk(ch):
            continue
        aid = ch["anchor_id"]
        text_raw = ch.get("text_raw", "")
        text_norm = ch.get("text_norm", text_raw)

        syn_entry = synonyms.get(aid, {})
        syn_list_cfg = syn_entry.get("synonyms", []) if isinstance(syn_entry, dict) else []
        syn_weight = float(syn_entry.get("weight", 1.0)) if isinstance(syn_entry, dict) else 1.0
        syn_list_inline = extract_inline_synonyms(text_raw)
        syn_all = []
        seen = set()
        for arr in [syn_list_cfg, syn_list_inline]:
            for s in arr:
                key = s.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    syn_all.append(s)

        pain_point_id = syn_entry.get("pain_point_id", "") if isinstance(syn_entry, dict) else ""
        insight_refs = syn_entry.get("insight_refs", []) if isinstance(syn_entry, dict) else []
        ch["taxonomy_refs"] = {"pain_point_id": pain_point_id, "insight_refs": insight_refs}
        ch["synonyms"] = syn_all

        tokens = tokenize(text_norm)
        rep = max(1, int(round(1.5 * syn_weight)))
        for syn in syn_all:
            ptok = phrase_token(syn)
            tokens.extend([ptok] * rep)

        doc_for_embed = text_norm if len(text_norm) <= 5000 else text_norm[:5000]

        id_map.append(aid)
        meta_map[aid] = ch.get("meta", {})
        srctext_map[aid] = text_raw
        docs.append(doc_for_embed)
        bm25_docs.append(tokens)

    if not docs:
        print("ERROR: no documents after filtering. Check filters or chunking.", file=sys.stderr)
        sys.exit(1)

    print(f"[build] Building BM25 over {len(bm25_docs)} docs")
    bm25 = BM25Okapi(bm25_docs)

    print(f"[build] Encoding embeddings for {len(docs)} docs")
    X = np.array(model.encode(docs, show_progress_bar=True, convert_to_numpy=True), dtype="float32")
    if HAVE_FAISS:
        index = faiss.IndexFlatIP(X.shape[1])
        norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
        Xn = X / norms
        index.add(Xn)
        faiss.write_index(index, str(project/"vault_index"/"faiss.index"))
    else:
        np.save(project/"vault_index"/"dense.npy", X)

    (project/"vault_index"/"bm25_corpus.json").write_text(json.dumps(bm25_docs), encoding="utf-8")
    (project/"vault_index"/"id_map.json").write_text(json.dumps(id_map, indent=2), encoding="utf-8")
    (project/"vault_index"/"meta.json").write_text(json.dumps(meta_map, indent=2), encoding="utf-8")
    with open(project/"vault_index"/"text_store.jsonl", "w", encoding="utf-8") as f:
        for aid in id_map:
            txt = srctext_map[aid]
            snippet = txt[:600]
            f.write(json.dumps({"anchor_id": aid, "snippet": snippet}, ensure_ascii=False) + "\n")

    manifest = {
        "built_at": now_iso(),
        "models": {"embedding": (config.get("models") or {}).get("embedding"), "reranker": (config.get("models") or {}).get("reranker")},
        "counts": {"docs": len(docs)},
        "filters": config.get("filters", {}),
        "paths": {
            "id_map": "vault_index/id_map.json",
            "meta": "vault_index/meta.json",
            "bm25_corpus": "vault_index/bm25_corpus.json",
            "faiss_index": "vault_index/faiss.index" if HAVE_FAISS else None,
            "dense": "vault_index/dense.npy" if not HAVE_FAISS else None,
            "text_store": "vault_index/text_store.jsonl"
        }
    }
    (project/"vault_index"/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status":"ok","message":"Index built","docs":len(docs),"faiss":HAVE_FAISS,"manifest":"vault_index/manifest.json"}, indent=2))

def query(project: Path, q: str, k: int, threshold_mode: str):
    cfg_file = project/"configs"/"config.yml"
    if not cfg_file.exists():
        cfg_file = project/"configs"/"config.yaml"
    config = load_yaml(cfg_file)

    index_dir = project/"vault_index"
    manifest = json.loads((index_dir/"manifest.json").read_text(encoding="utf-8"))
    id_map = json.loads((index_dir/"id_map.json").read_text(encoding="utf-8"))
    meta_map = json.loads((index_dir/"meta.json").read_text(encoding="utf-8"))
    bm25_docs = json.loads((index_dir/"bm25_corpus.json").read_text(encoding="utf-8"))

    thr = config.get("thresholds") or {}
    strict = float(thr.get("strict", 0.35))
    lenient = float(thr.get("lenient", 0.25))
    thresh = strict if threshold_mode == "strict" else lenient

    emb_model_name = (config.get("models") or {}).get("embedding", "all-MiniLM-L6-v2")
    model = SentenceTransformer(emb_model_name)

    bm25 = BM25Okapi(bm25_docs)

    q_tokens = tokenize(q) + [phrase_token(q)]
    bm25_scores = bm25.get_scores(q_tokens)

    if (index_dir/"faiss.index").exists():
        import faiss
        index = faiss.read_index(str(index_dir/"faiss.index"))
        q_vec = model.encode([q], convert_to_numpy=True)[0].astype("float32")
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
        q_vec = model.encode([q], convert_to_numpy=True)[0].astype("float32")
        norms = np.linalg.norm(X, axis=1) * (np.linalg.norm(q_vec) + 1e-9)
        emb_scores = (X @ q_vec) / (norms + 1e-9)

    def z_norm(a):
        a = np.array(a, dtype="float32")
        mu = a.mean(); sd = a.std() + 1e-6
        return (a - mu) / sd
    s_bm25 = z_norm(bm25_scores)
    s_emb = z_norm(emb_scores)
    combo = 0.5*s_bm25 + 0.5*s_emb

    topN = int(max(12, k*2))
    idx_sorted = list(np.argsort(-combo)[:topN])

    if X is None:
        selected = idx_sorted[:k]
    else:
        selected_local = mmr(X[idx_sorted], q_vec, k=k, lambda_=(config.get("retrieval") or {}).get("mmr_lambda", 0.7))
        selected = [idx_sorted[i] for i in selected_local]

    best = float(combo[selected[0]]) if selected else 0.0
    if best < thresh or not selected:
        print(json.dumps({"query": q, "results": [], "note": f"no result above {threshold_mode} threshold ({thresh})"}, indent=2))
        return

    text_store = {}
    with open(index_dir/"text_store.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            text_store[obj["anchor_id"]] = obj["snippet"]
    results = []
    for ix in selected[:k]:
        aid = id_map[ix]
        m = meta_map.get(aid, {})
        snippet = text_store.get(aid, "")[:200].replace("\n"," ")
        results.append({
            "anchor_id": aid,
            "score": float(combo[ix]),
            "snippet": snippet,
            "source_doc": m.get("source_doc"),
            "page": m.get("page_start")
        })

    pack = {
        "query": q,
        "filters": config.get("filters", {}),
        "results": results,
        "coverage": {},
        "retrieval_meta": {
            "k": k,
            "pipeline": ["bm25", "embed", "mmr"],
            "embedding_model": emb_model_name,
            "reranker": None,
            "threshold": threshold_mode
        }
    }
    print(json.dumps(pack, indent=2))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build BM25 + embedding index")
    b.add_argument("--project", required=True, help="Path to rag_project")

    q = sub.add_parser("query", help="Test a query against the hybrid index")
    q.add_argument("--project", required=True, help="Path to rag_project")
    q.add_argument("--q", required=True, help="Query string")
    q.add_argument("--k", type=int, default=8, help="Top k to return (default 8)")
    q.add_argument("--threshold", choices=["strict","lenient"], default="strict")

    args = ap.parse_args()
    project = Path(args.project).resolve()

    if args.cmd == "build":
        build(project)
    elif args.cmd == "query":
        query(project, args.q, args.k, args.threshold)

if __name__ == "__main__":
    main()
