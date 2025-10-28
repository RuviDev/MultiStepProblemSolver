from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import re
import asyncio
import pickle
import numpy as np
import os, sys, json, re, argparse, hashlib, html
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from rich.console import Console
from rich.markdown import Markdown

import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from openai import AsyncOpenAI
client = AsyncOpenAI()

# ---------- Configuration ----------
BASE   = Path(__file__).resolve().parents[1]
IDX    = BASE / "5_index"
CHUNKS = BASE / "4_chunks"

LLM_MODEL     = os.environ.get("RAG_LLM_MODEL", "gpt-4o-mini")
PLANNER_MODEL = os.environ.get("RAG_PLANNER_MODEL", LLM_MODEL)
RERANK_MODEL  = os.environ.get("RAG_RERANK_MODEL", LLM_MODEL)

ALLOW_GENERAL = os.environ.get("RAG_ALLOW_GENERAL_KNOWLEDGE", "false").lower() == "true"
MAX_GENERAL_P = float(os.environ.get("RAG_MAX_GENERAL_PERCENT", "0.25"))

# ---------- Helpers ----------
def compose_answer_question(current: str, prev: Optional[str], plan: Dict[str, Any]) -> str:
    """
    Build the exact question the writer/validator should answer.
    If the planner linked the previous turn, include it strictly as context.
    """
    if prev and plan.get("link_prev"):
        prev_short = prev.strip()
        if len(prev_short) > 500:
            prev_short = prev_short[:500] + "..."
        return (
            f"{current}\n\n"
            "[Context from previous turn — use ONLY to clarify the current prompt; "
            "do NOT answer it independently.]\n"
            f"Previous question: {prev_short}"
        )
    return current

def load_meta(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows

def tokenize_lex(s: str):
    # keep exact original lexical behavior
    return re.findall(r"[A-Za-z0-9_]+", s.lower())

def latest_chunks_path(doc_id: str) -> Path | None:
    paths = sorted((CHUNKS / doc_id).glob("*_chunks.jsonl"))
    return paths[-1] if paths else None

def load_chunk_record(chunk_id: str) -> Dict[str, Any] | None:
    # original behavior: chunks live under CHUNKS/<DOCID>/*_chunks.jsonl
    doc_id = chunk_id.split(":")[0]
    fp = latest_chunks_path(doc_id)
    if not fp:
        return None
    with fp.open("r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("chunk_id") == chunk_id:
                return r
    return None

# ---------- Phase 01: index loading ----------
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

# --- Cached index (load once, reuse across requests) ---
_INDEX: Tuple[List[Dict[str,Any]], BM25Okapi, List[str], SentenceTransformer, faiss.Index, Dict[str,Any]] | None = None
_INDEX_LOCK = asyncio.Lock()

async def get_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    async with _INDEX_LOCK:
        if _INDEX is not None:
            return _INDEX
        # offload heavy I/O/CPU to a worker
        _INDEX = await asyncio.to_thread(load_index)
        return _INDEX

# ---------- Phase 02: retrieval primitives ----------
def vec_search(q: str, model: SentenceTransformer, index: faiss.Index, topk=50):
    # original synchronous behavior preserved (we run caller in a thread)
    qv = model.encode([q], normalize_embeddings=True).astype("float32")
    sims, idxs = index.search(qv, topk)
    return idxs[0].tolist(), sims[0].tolist()

def bm25_search(q: str, bm25: BM25Okapi, bm25_ids: List[str], topk=50):
    toks = tokenize_lex(q)
    scores = bm25.get_scores(toks)
    order = np.argsort(scores)[::-1][:topk]
    return [(bm25_ids[i], scores[i]) for i in order]

def rrf_fuse(ranklists: Dict[str, Dict[str,int]], k: int = 60) -> Dict[str, float]:
    # original RRF accumulation (sum)
    scores: Dict[str, float] = {}
    for ranks in ranklists.values():
        for cid, r in ranks.items():
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
    return scores

# ---------- Phase 05 steps ----------
async def llm_plan_queries_old(question: str) -> Dict[str,Any]:
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
    resp = await client.responses.create(
        model=PLANNER_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    text = resp.output_text
    try:
        out = json.loads(text)
    except Exception:
        # fallback: naive extraction
        qs = re.findall(r'\"queries\"\\s*:\\s*\\[(.*?)\\]', text, flags=re.S)
        queries = []
        if qs:
            queries = [q.strip().strip('\"') for q in qs[0].split(',') if q.strip()]
        out = {"queries": queries or [question]}
    # defaults preserved
    out.setdefault("queries", [question])
    out.setdefault("doc_filters", [])
    out.setdefault("style", "concise")
    out.setdefault("tone", "plain")
    out.setdefault("format", ["sections", "bullets"])
    out.setdefault("audience", "practitioner")
    out.setdefault("allow_general_knowledge", False)
    return out

# --- replace the existing signature + body header of llm_plan_queries with this ---
async def llm_plan_queries(
    question: str,
    prev_enc: str | None = None,
) -> Dict[str, Any]:
    """
    Multi-query + presentation plan with previous-turn awareness (LLM-only).
    If prev_enc is provided, the planner decides whether the current question
    depends on/relates to it. The returned `queries` reflect that decision.
    """
    sys_msg = (
        "You are a query planner for a private RAG system.\n"
        "You may be given the previous user question from the same chat.\n"
        "First decide if the current question depends on or is meaningfully related "
        "to the previous one. ONLY if related, incorporate it when creating sub-queries.\n\n"
        "Return STRICT JSON with fields:\n"
        "{\n"
        "  \"link_prev\": true|false,\n"
        "  \"why\": \"short reason\",\n"
        "  \"queries\": [\"...\"],\n"
        "  \"doc_filters\": [\"DOC01\"|\"DOC02\"|\"DOC03\"...],\n"
        "  \"style\": \"concise|tutorial|step_by_step|deep_dive|executive_summary\",\n"
        "  \"tone\": \"plain|technical|persuasive\",\n"
        "  \"format\": [\"bullets\"|\"table\"|\"sections\"|\"detailed_report\"|\"summary_with_table\"|\"infographic_style\"],\n"
        "  \"audience\": \"novice|practitioner|expert\",\n"
        "  \"allow_general_knowledge\": false,\n"
        "  \"notes\": \"short\"\n"
        "}\n"
        "Rules:\n"
        "- If NOT related, ignore the previous turn entirely and plan queries only from the current question.\n"
        "- Keep queries specific and disjoint; 2–4 items.\n"
        "- Prefer entity- and facet-focused sub-queries."
    )

    payload = { "question": question }
    if prev_enc is not None:
        payload["previous_question"] = prev_enc

    user_msg = json.dumps(payload, ensure_ascii=False)

    resp = await client.responses.create(
        model=PLANNER_MODEL,
        input=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
    )
    text = resp.output_text

    # Robust parse; conservative fallback = treat as unrelated.
    try:
        out = json.loads(text)
    except Exception:
        out = {
            "link_prev": False,
            "why": "planner-json-parse-failed; defaulting to unrelated",
            "queries": [question],
            "doc_filters": [],
            "style": "concise",
            "tone": "plain",
            "format": ["sections", "bullets"],
            "audience": "practitioner",
            "allow_general_knowledge": False,
            "notes": "",
        }

    # Normalize defaults if fields are missing
    out.setdefault("link_prev", False)
    out.setdefault("why", "")
    out.setdefault("queries", [question])
    out.setdefault("doc_filters", [])
    out.setdefault("style", "concise")
    out.setdefault("tone", "plain")
    out.setdefault("format", ["sections", "bullets"])
    out.setdefault("audience", "practitioner")
    out.setdefault("allow_general_knowledge", False)
    out.setdefault("notes", "")
    return out


async def llm_rerank(question: str, candidate_ids: List[str], meta_map: Dict[str,Any], topn=10):
    """
    Ask LLM to pick the best chunk_ids. Provide compact snippets (breadcrumb + first ~400 chars).
    """
    items = []
    for cid in candidate_ids[:50]:  # bound prompt size
        m = meta_map[cid]
        rec = load_chunk_record(cid)
        if not rec: 
            continue
        txt = rec["text"].strip().replace("\r","")
        snippet = txt[:400]
        items.append({
            "chunk_id": cid,
            "breadcrumb": m.get("breadcrumb",""),
            "doc_id": m["doc_id"],
            "snippet": snippet
        })
    sys_msg = (
        "You are a retrieval reranker. "
        "Given the user's question and a list of candidates, select the most directly useful chunk_ids. "
        "Return JSON: { \"selected\": [\"chunk_id\", ...] }."
    )
    user_msg = json.dumps({"question": question, "candidates": items}, ensure_ascii=False)
    # print("===========|||| Prompt for the Reranker:\n", user_msg)
    resp = await client.responses.create(
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

async def llm_relevance_filter(question: str, candidate_ids: List[str], meta_map: Dict[str,Any], keep_cap: int=12) -> List[str]:
    """
    Strict filter: keep only directly helpful chunks.
    """
    # items = []
    # for cid in candidate_ids:
    #     rec = load_chunk_record(cid)
    #     if not rec: 
    #         continue
    #     snippet = rec["text"].strip().replace("\r","")[:350]
    #     items.append({
    #         "chunk_id": cid,
    #         "breadcrumb": rec.get("breadcrumb",""),
    #         "snippet": snippet
    #     })
    # sys_msg = (
    #     "You are a strict relevance filter for a RAG retriever. "
    #     "Return JSON: { \"keep\": [\"chunk_id\", ...], \"drop\": [\"chunk_id\", ...] }. "
    #     "Keep only chunks that directly help answer the question; drop tangents/duplicates."
    # )
    # user_msg = json.dumps({"question": question, "candidates": items}, ensure_ascii=False)
    # resp = await client.responses.create(
    #     model=RERANK_MODEL,
    #     input=[{"role":"system","content":sys_msg},
    #            {"role":"user","content":user_msg}],
    # )
    # try:
    #     data = json.loads(resp.output_text)
    #     keep = data.get("keep", [])
    #     if keep:
    #         return keep
    # except Exception:
    #     pass
    # return candidate_ids[:keep_cap]

    return candidate_ids

async def llm_sufficiency_gate(question: str, kept_ids: List[str]) -> Dict[str,Any]:
    """
    Estimate if RAG evidence is sufficient. Returns:
      { "sufficiency": float[0..1], "missing_aspects": [str, ...] }
    """
    summaries = []
    for cid in kept_ids[:16]:
        rec = load_chunk_record(cid)
        if not rec: 
            continue
        title = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        s = rec["text"].strip().replace("\r","")[:280]
        summaries.append({"chunk_id": cid, "title": title, "summary": s})
    sys_msg = (
        "You are a coverage estimator. Given a question and short evidence summaries, "
        "return JSON { \"sufficiency\": 0.0-1.0, \"missing_aspects\": [\"...\"] }. "
        "Be strict: if key parts seem missing, use ≤ 0.6."
    )
    user_msg = json.dumps({"question": question, "evidence": summaries}, ensure_ascii=False)
    resp = await client.responses.create(
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
        # fallback heuristic identical to before
        s = 0.4 + min(len(kept_ids), 10) * 0.05  # 0.4..0.9
        return {"sufficiency": max(0.0, min(1.0, s)), "missing_aspects": []}

def pack_context(chunk_ids: List[str], token_limit=6000) -> Tuple[str, List[Dict[str,Any]]]:
    """
    Build the context string under a token-ish budget using length as proxy.
    (Preserves original: bracketed id header, returns `included` as full chunk records.)
    """
    ctx_parts: List[str] = []
    included: List[Dict[str,Any]] = []
    total_chars = 0
    for cid in chunk_ids:
        rec = load_chunk_record(cid)
        if not rec:
            continue
        title = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        block = f"[{cid}] {title}\n{rec['text']}\n"
        new_total = total_chars + len(block)
        if new_total > token_limit * 4:  # rough char->token proxy
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
    # style knobs (preserved)
    style = style_plan.get("style", "concise")
    tone  = style_plan.get("tone", "plain")
    # fmt   = style_plan.get("format", ["sections", "bullets"])
    fmt   = style_plan.get("format", "auto")
    audience = style_plan.get("audience", "practitioner")
    allow_gk = allow_general or style_plan.get("allow_general_knowledge", False)

    # sys_msg = (
    #     "You are a domain-grounded assistant. Use ONLY the provided context as primary evidence.\n"
    #     f"If and only if coverage seems insufficient, you may add a small 'Background (general)' "
    #     f"subsection using general knowledge, capped at {int(max_general_fraction*100)}% of the answer.\n\n"
    #     "Policy for final answer:\n"
    #     "- Do NOT include plans, step-by-step execution, commands, shell output, code blocks, or deployment instructions.\n"
    #     "- Provide a final answer only; avoid “we will”, “next steps”, “let’s”, or similar planning/execution language.\n"
    #     "- If a previous question is shown, treat it ONLY as context to clarify the current prompt. Always answer the current prompt explicitly.\n"
    #     "- Keep it concise and user-facing. No pseudo-code or API calls. No production actions.\n\n"
    #     "Small-talk exception:\n"
    #     "- If the prompt is a brief greeting/pleasantry (e.g., “hi”, “hello”, “hey”, “thanks”, “good morning”), "
    #     "reply in a friendly tone with ONE short response (1–2 sentences). Do NOT reference evidence and do NOT use sections.\n\n"
    #     "Formatting policy (adaptive — NOT a fixed template):\n"
    #     "- Default to short paragraphs. Use bullets ONLY when listing 3+ parallel items.\n"
    #     "- Use a tiny 2–3 column table ONLY for explicit comparisons/trade-offs.\n"
    #     "- Avoid headings unless the answer is long; never invent rigid headings like “Summary/Key Points/Details” unless the user asked.\n"
    #     "- Keep structure minimal for short replies (≤2 sentences = just one short paragraph)."
    # )
    sys_msg = (
        "You are a domain-grounded assistant. Use ONLY the provided context as primary evidence.\n"
        f"If and only if coverage seems insufficient, you may add a small 'Background (general)' "
        f"subsection using general knowledge, capped at {int(max_general_fraction*100)}% of the answer.\n\n"
        "Policy for final answer:\n"
        "- Do NOT include plans, step-by-step execution, commands, shell output, code blocks, or deployment instructions.\n"
        "- Provide a final answer only; avoid “we will”, “next steps”, “let’s”, or similar planning/execution language.\n"
        "- If a previous question is shown, treat it ONLY as context to clarify the current prompt. Always answer the current prompt explicitly.\n"
        "- Keep it concise and user-facing. No pseudo-code or API calls. No production actions.\n\n"
        "Small-talk exception:\n"
        "- If the prompt is a brief greeting/pleasantry (e.g., “hi”, “hello”, “hey”, “thanks”, “good morning”), "
        "reply in a friendly tone with ONE short response (1–2 sentences). Do NOT reference evidence and do NOT use sections.\n\n"
        "Formatting policy (adaptive — NOT a fixed template):\n"
        "- Default to short paragraphs.\n"
        "- Use **bold section headings** where needed appropriately; keep them brief (2–5 words).\n"
        "- You may prefix a single relevant emoji to a heading (e.g., 📌 **Overview**, ✅ **Recommendation**, ⚠️ **Caveats**); use sparingly (max one emoji per heading).\n"
        "- Use bullets ONLY when listing 3+ parallel items.\n"
        "- Use a tiny 2–3 column table ONLY for explicit comparisons/trade-offs.\n"
        "- Do NOT force a rigid template like “Summary/Key Points/Details” unless the user explicitly asks for it.\n"
        "- For very short replies (≤2 sentences), omit headings and bullet points entirely."
    )

    body_instructions = (
        "Write the answer with an adaptive structure as per the formatting policy above.\n"
        "- If the prompt IS small-talk: reply with ONE short friendly sentence (optionally ask how you can help). No headings, bullets, or evidence.\n"
        "- Otherwise: prefer 1–3 short paragraphs; add bullets ONLY for enumerations; add a tiny table ONLY if comparing options.\n"
        "- Keep it readable. Do NOT include bracketed ids in the body.\n"
        "- If you use any general knowledge, add a final sub-section titled 'Background (general)'."
    )
    plan_blob = {
        "style": style, "tone": tone, "format": fmt, "audience": audience,
        "allow_general_knowledge": allow_gk, "sufficiency": sufficiency,
        "missing_aspects": missing_aspects
    }
    user_msg = (
        f"QUESTION (audience: {audience}, style: {style}, tone: {tone}, format: {fmt}):\n{question}\n\n"
        f"INSTRUCTIONS:\n{body_instructions}\n\n"
        "EVIDENCE (primary source):\n" + context_str
    )
    resp = await client.responses.create(
        model=LLM_MODEL,
        input=[{"role":"system","content":sys_msg},
               {"role":"user","content":user_msg}],
    )
    return resp.output_text

async def llm_validate(question: str, kept_ids: List[str], draft: str) -> str:
    """
    Optional small self-check: ensure on-topic / no contradictions.
    """
    items = []
    for cid in kept_ids[:10]:
        rec = load_chunk_record(cid)
        if not rec:
            continue
        breadcrumb = rec.get("breadcrumb") or " > ".join(rec.get("section_path", []))
        s = rec["text"].strip().replace("\r","")[:350]
        items.append({"chunk_id": cid, "breadcrumb": breadcrumb, "snippet": s})
    sys_msg = (
        "You are a validator for a RAG answer. Return JSON exactly as:\n"
        "{ \"on_topic\": true|false, \"contradiction\": true|false, \"revision\": \"\" }\n\n"
        "Checks:\n"
        "1) The draft must directly answer the CURRENT PROMPT (the provided 'question'). Any previous question in the text is context only.\n"
        "2) No planning/execution language (e.g., 'let’s', 'we will', 'next steps'), no shell/CLI commands, and no fenced code blocks (```).\n"
        "3) Structure must be ADAPTIVE: short replies should be a short paragraph; bullets used ONLY for enumerations; "
        "tables ONLY for explicit comparisons; avoid rigid templates like 'Summary/Key Points/Details' unless explicitly requested.\n"
        "4) If the prompt is small-talk (greeting/pleasantry), a single friendly sentence with no sections/evidence is acceptable.\n"
        "5) The draft must not contradict the evidence snippets.\n\n"
        "If any issue is found, provide a concise, user-facing 'revision' that fixes it (convert rigid templates to balanced paragraphs/bullets as appropriate). "
        "Otherwise, leave 'revision' empty."
    )
    user_msg = json.dumps({"question": question, "evidence": items, "draft": draft}, ensure_ascii=False)
    resp = await client.responses.create(
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

# ---------- Hybrid retrieval ----------
def hybrid_search_multi(meta, bm25, bm25_ids, model, index, qset: List[str], allow_docs=None,
                        kvec=50, klex=50, fuse_top=60) -> List[str]:
    """
    Original synchronous hybrid (vector + BM25) per sub-query with RRF fusion,
    pooled across sub-queries (we'll call this in a worker thread).
    """
    pooled: Dict[str, float] = {}
    for q in qset:
        # vector
        idxs, _ = vec_search(q, model, index, topk=kvec)
        vec_pairs = []
        for pos, i in enumerate(idxs, start=1):
            if i < 0:
                continue
            cid = meta[i]["chunk_id"]
            if allow_docs and cid.split(":")[0] not in allow_docs:  # DOC filter
                continue
            vec_pairs.append((cid, pos))
        # bm25
        bres = bm25_search(q, bm25, bm25_ids, topk=klex)
        bm25_pairs = []
        for pos, (cid, _) in enumerate(bres, start=1):
            if allow_docs and cid.split(":")[0] not in allow_docs:
                continue
            bm25_pairs.append((cid, pos))
        # fuse (sum of RRF)
        fused = rrf_fuse({"vec": dict(vec_pairs), "bm25": dict(bm25_pairs)}, k=fuse_top)
        for cid, sc in fused.items():
            pooled[cid] = pooled.get(cid, 0.0) + sc
    ranked = [cid for cid, _ in sorted(pooled.items(), key=lambda x: x[1], reverse=True)]
    return ranked

# ---------- Orchestrator ----------
async def component8_rag_answer(*, user_question: str, prev_enc: str | None = None, top:int=10, kvec:int=50, klex:int=50, doc:str=None, step=None) -> Dict[str,Any]:
    """
    Returns:
      { "used": bool, "answer_md": str, "sources": [{"chunk_id":..., "breadcrumb":...}, ...] }
    """

    print("=="*30);print(f" ----| Starting Component 8 |")
    print(" ------| Previous Question: ", prev_enc)
    if step: await step(2.4, "RAG: initializing")

    # load index (cached)
    meta, bm25, bm25_ids, embed_model, faiss_index, cfg = await get_index()
    meta_map = {m["chunk_id"]: m for m in meta}

    ALLOWED_DOCS = {"DOC01", "DOC02", "DOC03", "DOC04", "DOC05", "DOC06"}

    if step: await step(2.5, "RAG: planning-------------------")
    plan = await llm_plan_queries(user_question, prev_enc)
    # print(" ------| Plan: ", plan)
    qset = plan.get("queries", [user_question])
    print(" ------| Queries: ", qset)

    # optional document filter
    # allow_docs = set(plan.get("doc_filters") or ([] if not doc else [doc]))
    allow_docs = None
    if doc:
        allow_docs.add(doc)
    print(" ------| Allowed Docs: ", allow_docs)

    answer_question = compose_answer_question(user_question, prev_enc, plan)
    print(" ------| Composed Question: ", answer_question)

    # retrieval pool (run sync function in worker so loop stays responsive)
    if step: await step(2.6, "RAG: retrieving-------------------")
    ranked_ids = await asyncio.to_thread(
        hybrid_search_multi, meta, bm25, bm25_ids, embed_model, faiss_index, qset,
        allow_docs or None, kvec, klex, 60
    )
    # print(" ------| Ranked IDs: ", ranked_ids)
    # if not ranked_ids:
    #     return {"used": False, "answer_md": "", "sources": []}

    # LLM rerank
    if step: await step(2.7, "RAG: rerank-------------------")
    chosen = await llm_rerank(user_question, ranked_ids, meta_map, topn=12)
    print(" ------| Chosen LLM Rerank: ", chosen)

    # strict relevance filter
    if step: await step(2.8, "RAG: relevance filter-------------------")
    stitched = await llm_relevance_filter(user_question, chosen, meta_map, keep_cap=12)
    print(" ------| Relavence Filter Stitched: ", stitched)
    # if not stitched:
    #     print(" ------| No Relavent Chunks Found")
    #     return {"used": False, "answer_md": "", "sources": []}

    # pack context
    if step: await step(2.85, "RAG: packing context-------------------")
    context_str, included = pack_context(stitched, token_limit=6000)
    print(f" ------| ContextStr: {context_str}")

    # sufficiency & GK window
    if step: await step(2.9, "RAG: sufficiency-------------------")
    suff = await llm_sufficiency_gate(user_question, stitched)
    allow_general_final = (ALLOW_GENERAL or plan.get("allow_general_knowledge", False)) and (suff["sufficiency"] < 0.7)
    print(" ------| Allow General Knowledge: ", allow_general_final)
    print(" ------| Sufficiency Gate: ", suff)


    # compose
    if step: await step(3.0, "RAG: composing")
    draft = await llm_answer(
        answer_question, context_str, style_plan=plan,
        allow_general=allow_general_final,
        max_general_fraction=MAX_GENERAL_P,
        sufficiency=suff["sufficiency"],
        missing_aspects=suff.get("missing_aspects", []),
    )
    # print(" ------| LLM Draft Answer: ", draft)

    # validate
    if step: await step(3.1, "RAG: validating")
    final = await llm_validate(answer_question, stitched, draft)
    # print(" ------| LLM Final Answer: ", final)

    # sources (compact: id + breadcrumb) built from included records
    sources = [{"chunk_id": rec.get("chunk_id"), "breadcrumb": rec.get("breadcrumb","")} for rec in included]
    print(" ------| Sources Used: ", sources)

    return {"used": True, "answer_md": final, "sources": sources}

# ---------- CLI for local testing ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question", type=str)
    parser.add_argument("--doc", type=str, default=None)
    args = parser.parse_args()

    async def run():
        out = await component8_rag_answer(user_question=args.question, doc=args.doc)
        console = Console()
        console.print(Markdown(out.get("answer_md", "")))
        if out.get("sources"):
            print("\nSOURCES:")
            for s in out["sources"]:
                print("-", s["breadcrumb"], f"[id: {s['chunk_id']}]")

    asyncio.run(run())
