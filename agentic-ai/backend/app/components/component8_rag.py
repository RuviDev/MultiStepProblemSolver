from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import asyncio
import pickle
import numpy as np
import os, sys, json, re, argparse, pickle, hashlib, html

from pathlib import Path
from typing import List, Dict, Any, Tuple
from rich.console import Console
from rich.markdown import Markdown

import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from app.core.settings import settings
from openai import OpenAI

client = OpenAI()

# ---------- Configuration ----------
BASE = Path(__file__).resolve().parents[1]
IDX  = BASE / "5_index"
CHUNKS = BASE / "4_chunks"

LLM_MODEL      = os.environ.get("RAG_LLM_MODEL", "gpt-4o-mini")
PLANNER_MODEL  = os.environ.get("RAG_PLANNER_MODEL", LLM_MODEL)
RERANK_MODEL   = os.environ.get("RAG_RERANK_MODEL", LLM_MODEL)

ALLOW_GENERAL  = os.environ.get("RAG_ALLOW_GENERAL_KNOWLEDGE", "false").lower() == "true"
MAX_GENERAL_P  = float(os.environ.get("RAG_MAX_GENERAL_PERCENT", "0.25"))

# ---------- helpers ----------
def load_meta(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows

def tokenize_lex(s: str):
    return re.findall(r"[A-Za-z0-9_]+", s.lower())

def latest_chunks_path(doc_id: str) -> Path:
    paths = sorted((CHUNKS / doc_id).glob("*_chunks.jsonl"))
    return paths[-1] if paths else None

def load_chunk_record(chunk_id: str) -> Dict[str,Any]:
    doc_id = chunk_id.split(":")[0]
    fp = latest_chunks_path(doc_id)
    if not fp: return None
    with fp.open("r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("chunk_id") == chunk_id:
                return r
    return None

def load_index():
    # meta order == FAISS order
    meta = load_meta(IDX / "meta.jsonl")
    with open(IDX / "bm25.pkl", "rb") as f:
        bm25: BM25Okapi = pickle.load(f)
    bm25_doc_ids = json.loads((IDX / "bm25_doc_ids.json").read_text(encoding="utf-8"))
    cfg = json.loads((IDX / "index_config.json").read_text(encoding="utf-8"))
    model = SentenceTransformer(cfg["model_name"])  # same embedder used in build step
    index = faiss.read_index(str(IDX / "vector.faiss"))
    return meta, bm25, bm25_doc_ids, model, index, cfg

def vec_search(q: str, model, index, topk=50):
    qv = model.encode([q], normalize_embeddings=True).astype("float32")
    sims, idxs = index.search(qv, topk)
    return idxs[0].tolist(), sims[0].tolist()

def bm25_search(q: str, bm25: BM25Okapi, bm25_ids: List[str], topk=50):
    toks = tokenize_lex(q)
    scores = bm25.get_scores(toks)
    order = np.argsort(scores)[::-1][:topk]
    return [(bm25_ids[i], scores[i]) for i in order]

def rrf_fuse(ranklists: Dict[str, Dict[str,int]], k: int = 60) -> Dict[str, float]:
    scores = {}
    for ranks in ranklists.values():
        for cid, r in ranks.items():
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
    return scores

# ---------- Phase 05 steps ----------
async def llm_plan_queries(question: str) -> Dict[str,Any]:
    """
    Multi-query + presentation plan (style/tone/format/audience + allow_general_knowledge).
    """
    sys_msg = (
        "You are a query planner for a private RAG system. "
        "Given the user's question, output JSON with fields:\n"
        "{\n"
        "  \"queries\": [\"...\"],\n"
        "  \"doc_filters\": [\"DOC01\"|\"DOC02\"|\"DOC03\"...],\n"
        "  \"style\": \"concise|tutorial|step_by_step|deep_dive|executive_summary\",\n"
        "  \"tone\": \"plain|technical|persuasive\",\n"
        "  \"format\": [\"bullets\"|\"table\"|\"sections\"|\"examples\"|\"diagram_suggestion\"],\n"
        "  \"audience\": \"novice|practitioner|expert\",\n"
        "  \"allow_general_knowledge\": false,\n"
        "  \"notes\": \"short\"\n"
        "}\n"
        "Keep queries specific and disjoint; 2–4 items. Infer style from the wording when possible."
    )
    user_msg = f"Question: {question}"
    resp = client.responses.create(
        model=PLANNER_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    text = resp.output_text
    try:
        out = json.loads(text)
    except Exception:
        # fallback: naive extraction
        qs = re.findall(r'"queries"\s*:\s*\[(.*?)\]', text, flags=re.S)
        queries = []
        if qs:
            queries = re.findall(r'"([^"]+)"', qs[0])
        out = {
            "queries": queries or [question],
            "doc_filters": [],
            "style": "concise",
            "tone": "plain",
            "format": ["sections","bullets"],
            "audience": "practitioner",
            "allow_general_knowledge": False,
            "notes": "fallback parse"
        }
    if not out.get("queries"):
        out["queries"] = [question]
    # defaults
    out.setdefault("doc_filters", [])
    out.setdefault("style", "concise")
    out.setdefault("tone", "plain")
    out.setdefault("format", ["sections","bullets"])
    out.setdefault("audience", "practitioner")
    out.setdefault("allow_general_knowledge", False)
    return out

def hybrid_search_multi(meta, bm25, bm25_ids, model, index, qset: List[str], allow_docs=None,
                        kvec=50, klex=50, fuse_top=60) -> List[str]:
    """
    Run hybrid (vector + BM25) per sub-query, fuse with RRF, pool top IDs.
    """
    pooled = {}
    for q in qset:
        # vector
        idxs, _ = vec_search(q, model, index, topk=kvec)
        vec_pairs = []
        for pos, i in enumerate(idxs, start=1):
            if i < 0: continue
            cid = meta[i]["chunk_id"]
            if allow_docs and cid.split(":")[0] not in allow_docs:  # filter by DOCID
                continue
            vec_pairs.append((cid, pos))
        # bm25
        bres = bm25_search(q, bm25, bm25_ids, topk=klex)
        bm25_pairs = []
        for pos, (cid, _) in enumerate(bres, start=1):
            if allow_docs and cid.split(":")[0] not in allow_docs:
                continue
            bm25_pairs.append((cid, pos))
        # fuse
        fused = rrf_fuse({"vec": dict(vec_pairs), "bm25": dict(bm25_pairs)}, k=fuse_top)
        for cid, sc in fused.items():
            pooled[cid] = pooled.get(cid, 0.0) + sc
    # rank pooled across sub-queries
    ranked = [cid for cid, _ in sorted(pooled.items(), key=lambda x: x[1], reverse=True)]
    return ranked

async def llm_rerank(question: str, candidate_ids: List[str], meta_map: Dict[str,Any], topn=10):
    """
    Ask LLM to pick the best chunk_ids. Provide compact snippets (breadcrumb + first ~400 chars).
    """
    items = []
    for cid in candidate_ids[:50]:  # bound prompt size
        m = meta_map[cid]
        rec = load_chunk_record(cid)
        if not rec: continue
        txt = rec["text"].strip().replace("\r","")
        snippet = txt[:400]
        items.append({
            "chunk_id": cid, "breadcrumb": m.get("breadcrumb",""),
            "doc_id": m["doc_id"], "snippet": snippet
        })
    sys_msg = (
        "You are a retrieval reranker. "
        "Given the user's question and a list of candidates, return JSON:\n"
        "{ \"selected\": [\"chunk_id\", ...] }\n"
        "Pick the best items (8–12). Prefer exact topical match, recency doesn't matter."
    )
    user_msg = json.dumps({"question": question, "candidates": items}, ensure_ascii=False)
    resp = client.responses.create(
        model=RERANK_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    try:
        data = json.loads(resp.output_text)
        chosen = data.get("selected", [])
    except Exception:
        chosen = [c["chunk_id"] for c in items[:10]]
    return chosen

async def llm_relevance_filter(question: str, candidate_ids: List[str], meta_map: Dict[str,Any], keep_cap=20) -> List[str]:
    """
    Gate out off-topic / low-signal chunks. Returns a pruned list of chunk_ids.
    """
    items = []
    for cid in candidate_ids[:keep_cap]:
        m = meta_map[cid]
        rec = load_chunk_record(cid)
        if not rec: continue
        snippet = rec["text"].strip().replace("\r","")[:350]
        items.append({"chunk_id": cid, "breadcrumb": m.get("breadcrumb",""), "snippet": snippet})
    sys_msg = (
        "You are a strict relevance filter for a RAG retriever. "
        "Return JSON: { \"keep\": [\"chunk_id\", ...], \"drop\": [\"chunk_id\", ...] }. "
        "Keep only chunks that directly help answer the question; drop tangents/duplicates."
    )
    user_msg = json.dumps({"question": question, "candidates": items}, ensure_ascii=False)
    resp = client.responses.create(
        model=RERANK_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    try:
        data = json.loads(resp.output_text)
        keep = data.get("keep", [])
        if keep: return keep
    except Exception:
        pass
    return candidate_ids[:keep_cap]

async def llm_sufficiency_gate(question: str, kept_ids: List[str]) -> Dict[str,Any]:
    """
    Estimate if RAG evidence is sufficient. Returns:
      { "sufficiency": float[0..1], "missing_aspects": [str, ...] }
    """
    summaries = []
    for cid in kept_ids[:16]:
        rec = load_chunk_record(cid)
        if not rec: continue
        title = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        s = rec["text"].strip().replace("\r","")[:280]
        summaries.append({"chunk_id": cid, "title": title, "summary": s})
    sys_msg = (
        "You are a coverage estimator. Given a question and short evidence summaries, "
        "return JSON { \"sufficiency\": 0.0-1.0, \"missing_aspects\": [\"...\"] }. "
        "Be strict: if key parts seem missing, use ≤ 0.6."
    )
    user_msg = json.dumps({"question": question, "evidence": summaries}, ensure_ascii=False)
    resp = client.responses.create(
        model=RERANK_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    try:
        data = json.loads(resp.output_text)
        s = float(data.get("sufficiency", 0.5))
        missing = data.get("missing_aspects", [])
        return {"sufficiency": max(0.0, min(1.0, s)), "missing_aspects": missing}
    except Exception:
        # heuristic fallback based on kept evidence count
        s = 0.4 + min(len(kept_ids), 10) * 0.05  # crude: 0.4..0.9
        return {"sufficiency": max(0.0, min(1.0, s)), "missing_aspects": []}

def pack_context(chunk_ids: List[str], token_limit=6000) -> Tuple[str, List[Dict[str,Any]]]:
    """
    Build the context string under a token-ish budget using length as proxy.
    """
    ctx_parts = []
    included = []
    total_chars = 0
    for cid in chunk_ids:
        rec = load_chunk_record(cid)
        if not rec: continue
        title = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        block = f"[{cid}] {title}\n{rec['text']}\n"
        new_total = total_chars + len(block)
        if new_total > token_limit*4:  # rough char->token proxy
            break
        ctx_parts.append(block)
        included.append(rec)
        total_chars = new_total
    return "\n---\n".join(ctx_parts), included

async def llm_answer(question: str, context_str: str, style_plan: Dict[str,Any],
               allow_general: bool, max_general_fraction: float,
               sufficiency: float, missing_aspects: List[str]) -> str:
    """
    Compose a clean, style-aware answer. No inline bracketed IDs.
    """
    # style knobs
    style   = style_plan.get("style", "concise")
    tone    = style_plan.get("tone", "plain")
    fmt     = style_plan.get("format", ["sections","bullets"])
    audience= style_plan.get("audience", "practitioner")

    sys_msg = (
        "You are a careful RAG answerer.\n"
        "Grounding rule: Prefer facts from the provided Context. "
        "Do NOT include bracketed ids or citations in the body. "
        "If the Context seems insufficient and 'allow_general_knowledge=true', "
        f"you may add a small amount of general background ONLY for the listed missing aspects, "
        f"clearly separated, and not exceeding {int(max_general_fraction*100)}% of the final text. "
        "Never contradict the Context. If something is unknown, say so briefly.\n\n"
        "Structure rule: Produce clean Markdown. Use this template and adapt based on style/tone/audience:\n"
        "## TL;DR\n"
        "- 1–3 sentences with the direct answer\n\n"
        "## Key Points\n"
        "- 3–7 bullets\n\n"
        "## Details\n"
        "Short paragraphs, bullets, and (if helpful) small tables. "
        "If the question implies a comparison, include a small table.\n\n"
        "Formatting: keep it readable. No bracketed ids in the body. "
        "If you use any general knowledge, add a sub-section titled 'Background (general)' at the end."
    )

    plan_blob = {
        "style": style, "tone": tone, "format": fmt, "audience": audience,
        "allow_general_knowledge": allow_general,
        "sufficiency": sufficiency,
        "missing_aspects": missing_aspects
    }

    user_msg = (
        "Question:\n" + question + "\n\n"
        "Plan:\n" + json.dumps(plan_blob, ensure_ascii=False) + "\n\n"
        "Context (use this as primary source):\n" + context_str
    )

    resp = client.responses.create(
        model=LLM_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    return resp.output_text

async def llm_validate(question: str, included_meta: List[Dict[str,Any]], draft: str) -> str:
    """
    Optional small self-check: ensure on-topic / no contradictions.
    """
    items = []
    for r in included_meta[:10]:
        items.append({
            "chunk_id": r.get("chunk_id"),
            "breadcrumb": r.get("breadcrumb") or " > ".join(r.get("section_path", [])),
            "summary": r.get("text","")[:280]
        })
    sys_msg = (
        "You are a validator for a RAG answer. "
        "Given a question, evidence list, and a draft answer, return JSON:\n"
        "{ \"on_topic\": true|false, \"contradiction\": true|false, \"revision\": \"\" }\n"
        "If off-topic or contradictory, provide a short revised answer that fixes it."
    )
    user_msg = json.dumps({"question": question, "evidence": items, "draft": draft}, ensure_ascii=False)
    resp = client.responses.create(
        model=RERANK_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    try:
        data = json.loads(resp.output_text)
        if not data.get("on_topic", True) or data.get("contradiction", False):
            if data.get("revision"):
                return data["revision"]
    except Exception:
        pass
    return draft

async def component8_rag_answer(*, user_question: str, top:int=10, kvec:int=50, klex:int=50, doc:str=None, step=None) -> Dict[str,Any]:
    """
    Returns:
      { "used": bool, "answer_md": str, "sources": [{"chunk_id":..., "breadcrumb":...}, ...] }
    """
    if step: await step(2.4, "RAG: initializing")
    # load index
    meta, bm25, bm25_ids, embed_model, faiss_index, cfg = load_index()
    meta_map = {m["chunk_id"]: m for m in meta}

    if step: await step(2.5, "RAG: planning")
    # plan queries + style
    plan = await llm_plan_queries(user_question)
    qset = plan.get("queries", [user_question])
    allow_docs = set(plan.get("doc_filters") or ([] if not doc else [doc]))
    if doc:
        allow_docs.add(doc)

    # retrieval pool
    if step: await step(2.6, "RAG: retrieving")
    ranked_ids = hybrid_search_multi(
        meta, bm25, bm25_ids, embed_model, faiss_index, qset,
        allow_docs=allow_docs or None, kvec=kvec, klex=klex, fuse_top=60
    )
    if not ranked_ids:
        print("No candidates found.")
        return {"used": False, "answer_md": "", "sources": []}

    if step: await step(2.7, "RAG: rerank")
    chosen = await llm_rerank(user_question, ranked_ids, meta_map, topn=top)

    if step: await step(2.8, "RAG: relevance filter")
    filtered = await llm_relevance_filter(user_question, chosen, meta_map, keep_cap=max(12, top))

    # neighbor stitching + pack
    stitched = filtered
    stitched = list(dict.fromkeys(stitched))  # de-dupe but keep order
    stitched = stitched[:max(12, top)]
    stitched = list(dict.fromkeys(stitched + []))  # (placeholder if you later add extra neighbors)
    stitched = list(dict.fromkeys(stitched))  # ensure unique
    # you can re-enable neighbor expansion by replacing the 3 lines above with:
    # stitched = expand_neighbors(filtered, meta_map, budget_extra=6)

    context_str, included = pack_context(stitched, token_limit=6000)

    if step: await step(2.9, "RAG: sufficiency")
    suff = await llm_sufficiency_gate(user_question, stitched)
    allow_general_final = (ALLOW_GENERAL or plan.get("allow_general_knowledge", False)) and (suff["sufficiency"] < 0.7)

    if step: await step(3.0, "RAG: composing")
    draft = await llm_answer(
        user_question, context_str, style_plan=plan,
        allow_general=allow_general_final,
        max_general_fraction=MAX_GENERAL_P,
        sufficiency=suff["sufficiency"],
        missing_aspects=suff.get("missing_aspects", []),
    )

    if step: await step(3.1, "RAG: validating")
    final = await llm_validate(user_question, included, draft)

    # build a simple Sources section like the CLI (optional)
    sources = []
    for rec in included[: top + 6]:
        cid = rec["chunk_id"]
        breadcrumb = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        sources.append({"chunk_id": cid, "breadcrumb": html.unescape(breadcrumb)})

    # You can append sources to markdown if you want:
    # final += "\n\n---\n**Sources**\n" + "\n".join(f"- [{s['chunk_id']}] {s['breadcrumb']}" for s in sources)

    return {"used": True, "answer_md": final, "sources": sources}

