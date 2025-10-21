
import re, math
from typing import List, Dict, Any

_word_re = re.compile(r"[A-Za-z0-9_+/#-]+")
def tokens(text: str): return [t.lower() for t in _word_re.findall(text.lower())]

def score_keyword_overlap(text: str, phrases, weight_phrase=2.0, weight_token=1.0):
    if not phrases: return 0.0
    tset = set(tokens(text)); score = 0.0; tl = text.lower()
    for ph in phrases:
        phl = (ph or "").lower()
        if phl and phl in tl: score += weight_phrase
        for tk in tokens(phl):
            if tk in tset: score += weight_token
    return score

def softmax(xs):
    if not xs: return []
    m = max(xs); exps = [math.exp(x - m) for x in xs]; s = sum(exps) or 1.0
    return [e/s for e in exps]

def map_role(prompt_text: str, role_catalog: Dict[str, Any]):
    roles = role_catalog.get("roles", []); scores = []
    for r in roles:
        syns = r.get("synonyms", []) + [r.get("title","")]
        scores.append(score_keyword_overlap(prompt_text, syns, 2.5, 1.2))
    if not roles: return {"best": None, "alternates": [], "scores": []}
    probs = softmax(scores); best_idx = max(range(len(probs)), key=lambda i: probs[i])
    ranked = sorted([(i,probs[i]) for i in range(len(probs))], key=lambda x: x[1], reverse=True)
    best = {"role": roles[best_idx]["id"], "prob": probs[best_idx], "raw": scores[best_idx]}
    alts = [{"role": roles[i]["id"], "prob": p} for i,p in ranked[1:3] if p > 0.05]
    return {"best": best, "alternates": alts, "scores": scores}

def map_pain_points(prompt_text: str, gpp: Dict[str, Any], top_k=3):
    items = gpp.get("pain_points", []); scored = []
    for p in items:
        phrases = p.get("synonyms", []) + p.get("signals", []) + [p.get("title","")]
        scored.append((p["id"], score_keyword_overlap(prompt_text, phrases, 2.2, 1.0)))
    scored.sort(key=lambda x: x[1], reverse=True)
    probs = softmax([s for _,s in scored])
    ranked = [{"id": pid, "prob": probs[i] if probs else 0.0, "raw": scored[i][1]} for i,(pid,_) in enumerate(scored)]
    primary = [r for r in ranked[:top_k] if r["prob"] > 0.10]
    return {"ranked": ranked, "primary": primary}

def scope_gate_and_map(env: Dict[str, Any], request_envelope: Dict[str, Any]):
    prompt = request_envelope.get("prompt_clean",""); history = request_envelope.get("history_summary","")
    cand_pr = request_envelope.get("candidate_problem_record")

    role_catalog = env.get("catalog_data",{}).get("role_catalog",{})
    role_map = map_role(prompt + " " + history, role_catalog)
    role_best = role_map["best"]["role"] if role_map.get("best") and role_map["best"]["prob"] >= 0.25 else None
    if not role_best and cand_pr: role_best = cand_pr.get("employment_category")

    category_conflict = False
    if cand_pr and role_best and cand_pr.get("employment_category") and cand_pr.get("employment_category") != role_best:
        category_conflict = True

    gpp = env.get("catalog_data",{}).get("gpp_taxonomy",{})
    pp_map = map_pain_points(prompt + " " + history, gpp)
    primary_pp = [r["id"] for r in pp_map["primary"]]

    rp = role_map["best"]["prob"] if role_map.get("best") else 0.0
    pp_top = pp_map["primary"][0]["prob"] if pp_map["primary"] else 0.0
    mapping_confidence = round(0.6*pp_top + 0.4*rp, 3)

    ambiguous = mapping_confidence < 0.25; multi_intent = len(primary_pp) > 1
    out_of_scope = (role_best is None) and (pp_top < 0.08)
    queued_categories = [a["role"] for a in (role_map.get("alternates") or []) if a["prob"] >= 0.15]

    problem_context = {
        "employment_category": role_best,
        "pain_points": primary_pp[:1] if not multi_intent else [primary_pp[0]],
        "mapping_confidence": mapping_confidence,
        "ambiguous": ambiguous,
        "queued_categories": queued_categories
    }
    decisions = {
        "out_of_scope": out_of_scope,
        "category_conflict": category_conflict,
        "multi_intent": multi_intent,
        "ambiguous": ambiguous
    }
    debug = {"role_map": role_map, "pain_point_map": pp_map}
    return {"ok": True, "problem_context": problem_context, "decisions": decisions, "debug": debug}
