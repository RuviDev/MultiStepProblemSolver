#!/usr/bin/env python3
"""
Step 4 — Evaluation Harness for your RAG retriever
Computes Recall@K and MRR@K on configs/golden.json using the built index.

Usage:
  # Basic run (K = 1,3,5,8)
  python evaluate_rag.py run --project ./rag_project

  # Custom K list and threshold mode
  python evaluate_rag.py run --project ./rag_project --klist 1,3,8 --threshold strict

Outputs under <project>/vault_index/:
  - eval_summary.json
  - eval_details.jsonl
  - eval_report.md

Requirements:
  pip install rank-bm25 sentence-transformers numpy pyyaml
  # (faiss-cpu optional; used if present and you built a FAISS index)
"""

import argparse, json, os, sys, re, math
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

def norm_anchor_id(s: str) -> str:
    """Only for matching in evaluation, to be robust to dash/colon variations."""
    s2 = s.replace("—", "–").replace("-", "–")
    s2 = re.sub(r"\s+", " ", s2).strip()
    if s2.endswith(":"):
        s2 = s2[:-1]
    return s2

def load_index(project: Path):
    index_dir = project/"vault_index"
    id_map = json.loads((index_dir/"id_map.json").read_text(encoding="utf-8"))
    bm25_docs = json.loads((index_dir/"bm25_corpus.json").read_text(encoding="utf-8"))
    meta_map = json.loads((index_dir/"meta.json").read_text(encoding="utf-8"))
    manifest = json.loads((index_dir/"manifest.json").read_text(encoding="utf-8"))
    have_faiss = (index_dir/"faiss.index").exists()
    dense = None
    if not have_faiss:
        dense = np.load(index_dir/"dense.npy")
    # Build BM25 object
    bm25 = BM25Okapi(bm25_docs)
    return {
        "id_map": id_map,
        "bm25": bm25,
        "meta": meta_map,
        "manifest": manifest,
        "have_faiss": have_faiss,
        "dense": dense,
        "index_dir": index_dir
    }

def build_query_scores(q: str, state: Dict[str, Any], emb_model: SentenceTransformer, k: int, mmr_lambda: float):
    id_map = state["id_map"]
    bm25 = state["bm25"]
    have_faiss = state["have_faiss"]
    index_dir = state["index_dir"]
    dense = state["dense"]  # None if FAISS

    q_tokens = tokenize(q) + [phrase_token(q)]
    bm25_scores = bm25.get_scores(q_tokens)

    # Embedding similarity
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
        # no MMR if we don't have dense vectors available
        X = None
    else:
        X = dense
        q_vec = emb_model.encode([q], convert_to_numpy=True)[0].astype("float32")
        norms = np.linalg.norm(X, axis=1) * (np.linalg.norm(q_vec) + 1e-9)
        emb_scores = (X @ q_vec) / (norms + 1e-9)

    s_bm25 = z_norm(bm25_scores)
    s_emb = z_norm(emb_scores)
    combo = 0.5*s_bm25 + 0.5*s_emb

    # Candidate shortlist then MMR
    topN = int(max(12, k*2))
    idx_sorted = list(np.argsort(-combo)[:topN])
    if X is None:
        selected = idx_sorted[:k]
    else:
        sel_local = mmr(X[idx_sorted], q_vec, k=k, lambda_=mmr_lambda)
        selected = [idx_sorted[i] for i in sel_local]

    return combo, selected  # combo scores (global), selected indices (global)

def evaluate(project: Path, k_list: List[int], threshold_mode: str):
    # Load config + index
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

    state = load_index(project)

    emb_model_name = (config.get("models") or {}).get("embedding", "all-MiniLM-L6-v2")
    emb_model = SentenceTransformer(emb_model_name)

    # Load golden set
    golden_path = project/"configs"/"golden.json"
    if not golden_path.exists():
        raise FileNotFoundError(f"Missing golden.json at {golden_path}")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    if not isinstance(golden, list):
        raise ValueError("golden.json must be a list of {query, expected_anchor_ids, expected_pain_points}")

    id_map = state["id_map"]

    # Build a normed lookup of anchor IDs to speed matching
    id_map_norm = [norm_anchor_id(a) for a in id_map]
    anchor_to_index = {a: i for i, a in enumerate(id_map)}  # exact
    norm_to_indices = {}
    for i, a_norm in enumerate(id_map_norm):
        norm_to_indices.setdefault(a_norm, []).append(i)

    # Pain point mapping (optional): from synonyms.json
    syn_path = project/"configs"/"synonyms.json"
    painpoint_by_anchor = {}
    if syn_path.exists():
        syn = json.loads(syn_path.read_text(encoding="utf-8"))
        if isinstance(syn, dict):
            for aid, obj in syn.items():
                if isinstance(obj, dict):
                    pid = obj.get("pain_point_id", "")
                    if pid:
                        painpoint_by_anchor[aid] = pid

    # Eval accumulators
    details_path = project/"vault_index"/"eval_details.jsonl"
    summary_path = project/"vault_index"/"eval_summary.json"
    report_path = project/"vault_index"/"eval_report.md"

    total = len(golden)
    recall_at = {K: 0 for K in k_list}
    mrr_at = {K: 0.0 for K in k_list}

    misses = []  # queries with no hit by top max(k_list)
    hits_examples = []  # sample of good hits

    with open(details_path, "w", encoding="utf-8") as fout:
        for g in golden:
            q = g.get("query", "")
            expected_ids = [str(x) for x in g.get("expected_anchor_ids", [])]
            expected_norm = {norm_anchor_id(x) for x in expected_ids}
            expected_pain = set(g.get("expected_pain_points", []))

            # Build scores and selection using the same pipeline as the query tool
            combo, selected = build_query_scores(
                q, state, emb_model, k=max(k_list), mmr_lambda=mmr_lambda
            )

            # Filter by threshold
            if not selected:
                top_score = float("-inf")
            else:
                top_score = float(combo[selected[0]])
            if top_score < thr:
                top_indices = []
            else:
                top_indices = selected

            top_anchor_ids = [id_map[i] for i in top_indices]

            # Compute ranks for anchor-based success
            hit_rank = None
            hit_anchor = None
            for rank, aid in enumerate(top_anchor_ids, start=1):
                if norm_anchor_id(aid) in expected_norm:
                    hit_rank = rank
                    hit_anchor = aid
                    break

            for K in k_list:
                if hit_rank is not None and hit_rank <= K:
                    recall_at[K] += 1
                    mrr_at[K] += 1.0 / hit_rank

            # Pain-point match (optional, not used for metrics but logged)
            retrieved_pain = [painpoint_by_anchor.get(aid, "") for aid in top_anchor_ids]
            pain_hit = bool(expected_pain and any(p in expected_pain for p in retrieved_pain))

            # Log details
            rec = {
                "query": q,
                "expected_anchor_ids": expected_ids,
                "expected_pain_points": list(expected_pain),
                "top_results": [{"anchor_id": id_map[i], "score": float(combo[i])} for i in top_indices],
                "hit_rank": hit_rank,
                "hit_anchor": hit_anchor,
                "pain_point_hit": pain_hit,
                "threshold_passed": top_score >= thr if selected else False
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

            if hit_rank is None or hit_rank > max(k_list):
                misses.append(q)
            else:
                if len(hits_examples) < 10:
                    hits_examples.append({"query": q, "hit_anchor": hit_anchor, "rank": hit_rank})

    # Normalize metrics
    summary = {
        "queries": total,
        "k_list": k_list,
        "threshold": threshold_mode,
        "metrics": {
            "Recall@K": {K: (recall_at[K] / total) for K in k_list},
            "MRR@K": {K: (mrr_at[K] / total) for K in k_list}
        },
        "examples": {
            "hits": hits_examples,
            "misses_sample": misses[:20]
        }
    }
    Path(summary_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Markdown report
    lines = []
    lines.append("# RAG Evaluation Report")
    lines.append(f"- Total queries: **{total}**")
    lines.append(f"- Threshold mode: **{threshold_mode}**")
    lines.append("")
    lines.append("## Metrics")
    for K in k_list:
        lines.append(f"- Recall@{K}: **{summary['metrics']['Recall@K'][K]:.3f}**")
    for K in k_list:
        lines.append(f"- MRR@{K}: **{summary['metrics']['MRR@K'][K]:.3f}**")
    lines.append("")
    lines.append("## Sample Hits (first 10)")
    for h in hits_examples:
        lines.append(f"- “{h['query']}” → {h['hit_anchor']} (rank {h['rank']})")
    lines.append("")
    lines.append("## Sample Misses (first 20)")
    for q in misses[:20]:
        lines.append(f"- “{q}”")
    Path(report_path).write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "summary_path": str(summary_path),
        "details_path": str(details_path),
        "report_path": str(report_path),
        "metrics": summary["metrics"]
    }, indent=2))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    rp = sub.add_parser("run", help="Run evaluation on golden.json")
    rp.add_argument("--project", required=True, help="Path to rag_project")
    rp.add_argument("--klist", default="1,3,5,8", help="Comma-separated Ks (e.g., 1,3,8)")
    rp.add_argument("--threshold", choices=["strict","lenient"], default="strict")

    args = ap.parse_args()
    project = Path(args.project).resolve()
    k_list = [int(x) for x in args.klist.split(",") if x.strip()]

    if args.cmd == "run":
        evaluate(project, k_list, args.threshold)

if __name__ == "__main__":
    main()
