import pathlib, json
from typing import Dict, Any
from rag.query_builder import build_query
from rag.retrieve import retrieve as _retrieve

ROOT = pathlib.Path(__file__).resolve().parents[1]

async def query_rag_for_prompt(prompt: str, insight_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a rich query from prompt+insights, call retriever, return evidence pack.
    """
    qb = build_query(prompt, insight_state or {})
    pack = _retrieve(prompt=qb["query_text"],
                     anchor_hints=qb["anchor_hints"],
                     terms=qb["terms"],
                     topk_dense=24, topk_bm25=24, final_k=8)
    return pack
