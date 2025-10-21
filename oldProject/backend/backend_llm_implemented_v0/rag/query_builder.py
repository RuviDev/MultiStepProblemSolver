import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent

with open(ROOT / "insight_to_anchors.json", "r") as f:
    INSIGHT2ANCHORS = json.load(f)

def _insight_hints(insight_state: dict) -> tuple[list[str], list[str]]:
    """Return (anchor_hints, term_hints) from current insights."""
    anchors, terms = set(), set()
    for key, field in (insight_state or {}).items():
        if not field or "value" not in field: continue
        val = field["value"]
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            hkey = f"{key}.{v}"
            for aid in INSIGHT2ANCHORS.get(hkey, []):
                anchors.add(aid)
            # also add simple lexical terms to bias BM25
            terms.add(v.replace("_", " "))
    return list(anchors), list(terms)

def build_query(prompt: str, insight_state: dict) -> dict:
    """
    Build a 'rich query' used by retriever.
    Returns dict with: 'query_text', 'anchor_hints', 'terms'
    """
    anchor_hints, terms = _insight_hints(insight_state)
    parts = [prompt.strip()]
    if terms:
        parts.append("terms: " + ", ".join(sorted(set(terms))[:12]))
    if anchor_hints:
        parts.append("anchors: " + ", ".join(anchor_hints[:12]))
    return {
        "query_text": " | ".join(parts),
        "anchor_hints": anchor_hints,
        "terms": terms
    }
