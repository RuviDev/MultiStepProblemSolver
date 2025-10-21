import json, orjson, numpy as np, pathlib, re, heapq
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
import faiss

ROOT = pathlib.Path(__file__).resolve().parent
IDX = ROOT.parent / "rag_index"

# lazy globals
_BM25 = None
_TOK = None
_EMB = None
_FAISS = None
_META = None
_EMB_MODEL = None
_RERANKER = None

SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+(?=[A-Z0-9])")

def _lazy_load():
    global _BM25, _TOK, _EMB, _FAISS, _META, _EMB_MODEL, _RERANKER
    if _TOK is None:
        _TOK = np.load(IDX / "bm25_tokenized.npy", allow_pickle=True).tolist()
        _BM25 = BM25Okapi(_TOK)
    if _EMB is None:
        _EMB = np.load(IDX / "dense.npy")
        _FAISS = faiss.read_index(str(IDX / "faiss.index"))
    if _META is None:
        with open(IDX / "id_map.json", "r") as f:
            _META = {int(k): v for k, v in json.load(f).items()}
    if _EMB_MODEL is None:
        _EMB_MODEL = SentenceTransformer("intfloat/e5-small-v2")
    # Optional cross-encoder reranker (comment out if latency is critical)
    if _RERANKER is None:
        try:
            _RERANKER = CrossEncoder("bge-reranker-base")
        except Exception:
            _RERANKER = None

def _bm25_topk(query: str, k: int) -> List[Tuple[int, float]]:
    toks = query.lower().split()
    scores = _BM25.get_scores(toks)
    top = heapq.nlargest(k, enumerate(scores), key=lambda x: x[1])
    return [(i, float(s)) for i, s in top]

def _dense_topk(query: str, k: int) -> List[Tuple[int, float]]:
    q = _EMB_MODEL.encode([query], normalize_embeddings=True)
    D, I = _FAISS.search(q.astype("float32"), k)
    return [(int(i), float(d)) for i, d in zip(I[0], D[0])]

def _mmr(query_vec: np.ndarray, cand_idxs: List[int], lam: float, k: int) -> List[int]:
    """Maximal Marginal Relevance over dense vectors we already have."""
    cand_vecs = _EMB[cand_idxs]
    selected = []
    sim_to_query = cand_vecs @ query_vec.T  # cosine (normalized)
    remaining = set(range(len(cand_idxs)))
    while remaining and len(selected) < k:
        if not selected:
            i = int(np.argmax(sim_to_query))
            selected.append(i); remaining.remove(i)
            continue
        # diversity term: max sim to any selected
        sel_vecs = cand_vecs[selected]
        sims = []
        for ridx in remaining:
            div = np.max(sel_vecs @ cand_vecs[ridx].T)
            score = lam * sim_to_query[ridx] - (1 - lam) * div
            sims.append((score, ridx))
        ridx = max(sims, key=lambda x: x[0])[1]
        selected.append(ridx); remaining.remove(ridx)
    return [cand_idxs[i] for i in selected]

def _compress_snippets(text: str, query: str, max_bullets=4) -> List[str]:
    sents = SENT_SPLIT.split(text.strip())
    if not sents: return []
    # simple cosine selection using embedding model
    qs = _EMB_MODEL.encode([query], normalize_embeddings=True)[0]
    Ss = _EMB_MODEL.encode(sents, normalize_embeddings=True)
    sims = (Ss @ qs).tolist()
    top = heapq.nlargest(max_bullets, enumerate(sims), key=lambda x: x[1])
    bullets = []
    for idx, sc in top:
        s = sents[idx].strip()
        bullets.append(f"• {s}")
    return bullets

def retrieve(prompt: str, anchor_hints: List[str], terms: List[str], topk_dense=24, topk_bm25=24, final_k=8) -> Dict[str, Any]:
    """
    Return normalized evidence pack:
    {
      'query': '...',
      'results': [
         {'anchor_id': 'BND–...', 'score': 0.73, 'bullets': ['• ...','• ...'], 'source_doc': '...', 'chunk_id': 123}
      ]
    }
    """
    _lazy_load()
    # Build a strong query string
    rich_q = " | ".join([prompt.strip(),
                         f"terms: {', '.join(terms)}" if terms else "",
                         f"anchors: {', '.join(anchor_hints)}" if anchor_hints else ""]).strip(" |")

    # Candidate recall
    bm25 = _bm25_topk(rich_q, topk_bm25)
    dense = _dense_topk(rich_q, topk_dense)

    # unify candidate ids with normalized scores
    # z-norm each list then sum
    def znorm(scores):
        arr = np.array([s for _, s in scores], dtype=float)
        if arr.size == 0: return {}
        mu, sd = arr.mean(), arr.std() or 1.0
        return {i: (s - mu) / sd for (i, s) in scores}
    s_b = znorm(bm25)
    s_d = znorm(dense)
    cand = {}
    for i, s in s_b.items(): cand[i] = cand.get(i, 0) + s
    for i, s in s_d.items(): cand[i] = cand.get(i, 0) + s

    cand_idxs = list(cand.keys())
    if not cand_idxs:
        return {"query": rich_q, "results": []}

    # MMR diversification on dense space
    qv = _EMB_MODEL.encode([rich_q], normalize_embeddings=True)[0]
    mmr_idxs = _mmr(qv, cand_idxs, lam=0.7, k=min(final_k*2, len(cand_idxs)))

    # Optional reranker (cross-encoder)
    if _RERANKER:
        pairs = [[rich_q, " ".join([_META[i]["title"]])] for i in mmr_idxs]
        rerank_scores = _RERANKER.predict(pairs).tolist()
        ranked = [idx for _, idx in sorted(zip(rerank_scores, mmr_idxs), key=lambda z: z[0], reverse=True)]
        mmr_idxs = ranked

    # Take final_k, compress to bullets
    results = []
    chunks = orjson.loads(open(IDX / "chunks.jsonl","rb").read().splitlines()[0])  # dummy to get type; we won't load all
    # We need texts; safer to reopen lines by index (small set)
    with open(IDX / "chunks.jsonl", "rb") as f:
        lines = f.read().splitlines()
    for i in mmr_idxs[:final_k]:
        meta = _META[i]
        text = orjson.loads(lines[i])["text"]
        bullets = _compress_snippets(text, rich_q, max_bullets=4)
        results.append({
            "anchor_id": meta["anchor_id"],
            "score": float(i),   # you can replace with combined score if needed
            "bullets": bullets,
            "source_doc": meta["source_doc"],
            "chunk_id": i
        })
    return {"query": rich_q, "results": results}
