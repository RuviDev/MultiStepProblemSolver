# app/services/insight_engine.py
from __future__ import annotations
import re
import json
from typing import Dict, List, Tuple

from app.core.openai_client import client, REQUEST_TIMEOUT
from app.core.settings import settings, get_insights_model
from app.repositories.insight_vault_repo import InsightVaultRepo
from app.repositories.chat_insights_repo import ChatInsightsRepo
from motor.motor_asyncio import AsyncIOMotorDatabase


# Master prompt (VERBATIM as spec)
SYSTEM_PROMPT = """Output ONLY JSON with this schema:
{
  "decisions": [
    {
      "insightId":"...", "batchId":"...",
      "matchType":"QUESTION_AND_ANSWER"|"ANSWER_ONLY"|"QUESTION_ONLY",
      "matchedAnswerId":"A|B|...|null",
      "decisionConfidence":0.0,
      "evidence":["short exact quote(s) from the user text"]
    }
  ]
}
Rules:
- Use ONLY the provided answers/aliases; do NOT invent options.
- If the text directly expresses a listed answer/alias → ANSWER_ONLY with that matchedAnswerId.
- If the text supports the question AND clearly implies a listed answer → QUESTION_AND_ANSWER.
- If the text is about the question topic but no listed answer is clear → QUESTION_ONLY (matchedAnswerId=null).
- Do NOT output NO_MATCH items; include ONLY true matches.
- Be strict; prefer QUESTION_ONLY over guessing an answer.
- decisionConfidence ∈ [0,1].
- Ignore negated/obsolete statements (e.g., "not a problem anymore").
- Output JSON only. No prose.
"""

def _coerce_matched_answer_id(v):
    # Accept JSON null or the literal string "null"
    if v is None:
        return None
    if isinstance(v, str) and v.lower() == "null":
        return None
    if isinstance(v, str):
        return v
    # Be conservative: anything else -> None
    return None

def _parse_multi_answer_ids(raw: str, valid_ids: dict) -> list[str]:
    """
    Parse a pipe/comma/space separated string of answer IDs into a list of valid IDs.
    - Accepts delimiters: | , / whitespace
    - Trims, uppercases, dedupes
    - Filters to IDs present in valid_ids
    """
    if not isinstance(raw, str) or not raw.strip():
        return []
    # Split on | , / or whitespace
    parts = re.split(r"[|,/\s]+", raw.strip())
    seen, out = set(), []
    for p in parts:
        if not p:
            continue
        key = p.upper()
        if key == "NULL":
            continue
        if key in valid_ids and key not in seen:
            seen.add(key)
            out.append(key)
    return out

async def stage01_auto_infer(
    db: AsyncIOMotorDatabase,
    *,
    chatId: str,
    user_text: str,
) -> Dict:
    """
    Runs Stage-01 (Auto-Inference) end-to-end:
      - ensure session (vaultVersion)
      - compute taken/pending
      - LLM pass with full Vault Pack (strict JSON)
      - apply thresholds (0.75 auto-take; 0.60 question-only)
      - union touched batches
      - batch expansion (MUST)
      - return pendingByBatch + stats + touchedBatchIds
    """
    vault_repo = InsightVaultRepo(db)
    pcch_repo = ChatInsightsRepo(db)
    vaultVersion = settings.INSIGHT_VAULT_VERSION

    print(" ------| Using Insight vault version:", vaultVersion)

    # 1) Ensure session & read taken/pending
    await pcch_repo.ensure_session(chatId, vaultVersion)
    already_taken, already_pending = await pcch_repo.get_taken_and_pending(chatId)
    print(" ------| Already taken Insights:", already_taken)
    print(" ------| Already pending Insights:", already_pending)

    # 2) Build Vault Pack (active items only)
    vault_pack = await vault_repo.build_vault_pack()

    # 3) LLM call (strict JSON only)
    user_content = f"""USER:
TEXT:
<<<
{user_text}
>>>

VAULT_PACK:
{json.dumps(vault_pack, ensure_ascii=False)}
"""

    # print("========User content:", user_content[:500], "...")
    comp = await client.chat.completions.create(
        model=get_insights_model(),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=float(settings.INSIGHTS_TEMPERATURE),
        top_p=float(settings.INSIGHTS_TOP_P),
        timeout=REQUEST_TIMEOUT,
    )

    raw = comp.choices[0].message.content
    try:
        parsed = json.loads(raw or "{}")
    except Exception as e:
        raise ValueError(f"Insights Stage-01: Non-JSON response") from e

    decisions: List[Dict] = parsed.get("decisions") or []
    print(" ------| LLM decisions count:", len(decisions))
    print(" ------| LLM decisions sample:", decisions[:3])

    # Pre-build an insight index for validation
    insight_index = await vault_repo.build_insight_index()
    print(" ------| Pre-Built Insight index size:", len(insight_index))

    auto_taken_count = 0
    question_only_count = 0
    touched_batches: set[str] = set()

    # 4) Apply thresholds & write per decision
    print(" ------| Processing decisions:")
    for d in decisions:
        try:
            insightId = d["insightId"]
            batchId_from_llm = d["batchId"]
            matchType = d["matchType"]
            matchedAnswerId_raw = d.get("matchedAnswerId")
            decisionConfidence = float(d.get("decisionConfidence", 0))
            evidence = d.get("evidence") or []
        except Exception:
            # Skip malformed
            continue

        print(f" --------- | Decision: {insightId} / {batchId_from_llm} / {matchType} / {matchedAnswerId_raw} / {decisionConfidence} / {evidence}")
        # Validate insightId exists and active
        meta = insight_index.get(insightId)
        if not meta:
            continue
        batchId = meta["batchId"]
        if batchId_from_llm != batchId:
            # reject mismatched batch
            continue

        # If this insight is already taken, still mark the batch as touched
        # so Batch Expansion covers other insights in this batch, then skip.
        if insightId in already_taken:
            touched_batches.add(batchId)
            continue

        is_multi = bool(meta["isMultiSelect"])
        answers = meta["answers"]
        print(f" --------- | is_multi={is_multi}, answers={list(answers.keys())}")

        # Enforce allowed match types
        if matchType not in ("QUESTION_AND_ANSWER", "ANSWER_ONLY", "QUESTION_ONLY"):
            continue

        # Thresholds
        if matchType in ("QUESTION_AND_ANSWER", "ANSWER_ONLY") and decisionConfidence >= 0.75:
            # ans_id = _coerce_matched_answer_id(matchedAnswerId_raw)
            # print(f" --------- | coerced matchedAnswerId: {ans_id}")
            # if not ans_id or ans_id not in answers:
            #     # even on auto-take, must have a valid answerId
            #     continue

            # mode = "qa" if matchType == "QUESTION_AND_ANSWER" else "answer_only"
            # if is_multi:
            #     # Stage-01 schema returns a single answerId; store as single selection for now.
            #     await pcch_repo.write_auto_take_multi(
            #         chatId=chatId,
            #         batchId=batchId,
            #         insightId=insightId,
            #         answerIds=[ans_id],
            #         mode=mode,
            #         confidence=decisionConfidence,
            #         evidence=evidence,
            #         vaultVersion=vaultVersion,
            #     )
            # else:
            #     await pcch_repo.write_auto_take_single(
            #         chatId=chatId,
            #         batchId=batchId,
            #         insightId=insightId,
            #         answerId=ans_id,
            #         mode=mode,
            #         confidence=decisionConfidence,
            #         evidence=evidence,
            #         vaultVersion=vaultVersion,
            #     )

            # Multi-aware parsing
            mode = "qa" if matchType == "QUESTION_AND_ANSWER" else "answer_only"
            if is_multi:
                # Parse multiple selections like "B|D" (or with commas/spaces)
                parsed_ids = _parse_multi_answer_ids(matchedAnswerId_raw, answers)
                print(f" --------- | parsed multi matchedAnswerIds: {parsed_ids}")
                if not parsed_ids:
                    # No valid selections → skip auto-take
                    continue
                await pcch_repo.write_auto_take_multi(
                    chatId=chatId,
                    batchId=batchId,
                    insightId=insightId,
                    answerIds=parsed_ids,
                    mode=mode,
                    confidence=decisionConfidence,
                    evidence=evidence,
                    vaultVersion=vaultVersion,
                )
            else:
                # Single-select: keep existing behavior; if LLM returns "B|D", take the first valid
                ans_raw = _coerce_matched_answer_id(matchedAnswerId_raw)
                # If the model accidentally sent a delimited string, pick first valid
                candidate_ids = _parse_multi_answer_ids(ans_raw, answers) if isinstance(ans_raw, str) and ("|" in ans_raw or "," in ans_raw or " " in ans_raw or "/" in ans_raw) else [ans_raw]
                # Choose the first valid ID
                ans_id = next((cid for cid in candidate_ids if cid in answers), None)
                print(f" --------- | coerced single matchedAnswerId: {ans_id}")
                if not ans_id:
                    continue
                await pcch_repo.write_auto_take_single(
                    chatId=chatId,
                    batchId=batchId,
                    insightId=insightId,
                    answerId=ans_id,
                    mode=mode,
                    confidence=decisionConfidence,
                    evidence=evidence,
                    vaultVersion=vaultVersion,
                )

            
            auto_taken_count += 1
            touched_batches.add(batchId)

        elif matchType == "QUESTION_ONLY" and decisionConfidence >= 0.60:
            await pcch_repo.write_question_only(
                chatId=chatId,
                batchId=batchId,
                insightId=insightId,
                confidence=decisionConfidence,
                evidence=evidence,
                vaultVersion=vaultVersion,
            )
            question_only_count += 1
            touched_batches.add(batchId)

        # else: below thresholds → ignore

    # 5) Batch expansion (MUST) for all touched batches
    for b in list(touched_batches):
        candidate_ids = await vault_repo.list_active_insight_ids_by_batch(b)
        print(" ------| Batch expansion:", b, "candidates:", candidate_ids)
        await pcch_repo.batch_expand_pending(
            chatId=chatId,
            batchId=b,
            candidateInsightIds=candidate_ids,
            vaultVersion=vaultVersion,
        )

    # 6) pendingByBatch + stats
    pending_by_batch = await pcch_repo.list_pending_by_batch(chatId, list(touched_batches) or None)
    print(" ------| Pending by batch (touched):", pending_by_batch)
    stats = await pcch_repo.recompute_stats(chatId)
    print(" ------| Recomputed stats:", stats)
    # Track touched batches in session
    for b in touched_batches:
        await pcch_repo.union_touch_batch(chatId, b)

    return {
        "vaultVersion": vaultVersion,
        "touchedBatchIds": list(touched_batches),
        "pendingByBatch": pending_by_batch,
        "insightStats": stats.model_dump(),
        "autoTakenCount": auto_taken_count,
        "questionOnlyCount": question_only_count,
    }

