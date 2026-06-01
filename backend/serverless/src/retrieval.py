"""Symptom retrieval and scoring.

LLM이 추출한 symptom span을 그대로 믿지 않고, Asan-derived source JSON에서 만든
증상 문서를 대상으로 BM25 lexical score, Titan embedding vector score, label/alias
hint를 조합해 표준 증상명으로 매칭합니다.
"""

from decimal import Decimal

from clinical_terms import (
    IR_RED_FLAG_NAMES,
    SYMPTOM_RULES,
    is_symptom_like_span,
)
from settings import (
    HYBRID_ACCEPT_THRESHOLD,
    HYBRID_BM25_WEIGHT,
    HYBRID_CANDIDATE_K,
    HYBRID_MIN_BM25_SCORE,
    HYBRID_MIN_LABEL_SCORE,
    HYBRID_MIN_VECTOR_SCORE,
    HYBRID_TOP_K,
    HYBRID_VECTOR_WEIGHT,
    USE_TITAN_EMBEDDING,
)
from retrieval_documents import get_ir_index, get_symptom_name_by_id, preferred_canonical_name
from retrieval_embeddings import embed_text, get_doc_embeddings
from retrieval_scoring import cosine, direct_label_score, minmax_norm
from utils import (
    normalize_text,
)



def retrieve_symptom_docs(source_quote, normalized_text, span_name="", preferred_slot_id=""):
    """하나의 symptom span에 대해 BM25/vector/label 후보를 모아 상위 증상을 반환합니다."""
    docs, bm25 = get_ir_index()
    query = normalize_text(" ".join([source_quote or "", normalized_text or "", span_name or ""]))
    if not query:
        return []
    preferred_name = preferred_canonical_name(preferred_slot_id, span_name, normalized_text, source_quote)

    bm25_raw = bm25.scores(query)
    bm25_norm = minmax_norm(bm25_raw)
    q_emb = None
    vector_raw = [0.0] * len(docs)
    vector_error = ""
    if USE_TITAN_EMBEDDING:
        try:
            q_emb = embed_text(query)
        except Exception as exc:
            vector_error = str(exc)

    doc_embeddings = get_doc_embeddings(docs) if q_emb is not None else {}
    if q_emb is not None and doc_embeddings:
        for idx, doc in enumerate(docs):
            vector_raw[idx] = max(0.0, cosine(q_emb, doc_embeddings.get(doc["symptom_id"])))
    vector_norm = minmax_norm(vector_raw)

    candidate_k = max(HYBRID_CANDIDATE_K, HYBRID_TOP_K * 3)
    bm25_top = set(sorted(range(len(docs)), key=lambda i: bm25_norm[i], reverse=True)[:candidate_k])
    vector_top = set(sorted(range(len(docs)), key=lambda i: vector_norm[i], reverse=True)[:candidate_k]) if doc_embeddings else set()
    label_top = {
        idx
        for idx, doc in enumerate(docs)
        if direct_label_score(query, doc["display_name"]) >= 0.55 or doc["display_name"] == preferred_name
    }
    candidate_ids = bm25_top | vector_top | label_top
    if q_emb is not None and not doc_embeddings:
        # Packaged vector index is absent: still use Titan for the BM25/label candidates.
        for idx in list(candidate_ids):
            try:
                emb = embed_text(docs[idx].get("embedding_text", ""))
                vector_raw[idx] = max(0.0, cosine(q_emb, emb))
            except Exception as exc:
                vector_error = str(exc)
        candidate_vectors = [vector_raw[idx] for idx in candidate_ids]
        norm_lookup = dict(zip(candidate_ids, minmax_norm(candidate_vectors)))
        vector_norm = [norm_lookup.get(idx, 0.0) for idx in range(len(docs))]

    rows = []
    intersection_ids = bm25_top & (vector_top or candidate_ids)
    for idx in candidate_ids:
        doc = docs[idx]
        label = direct_label_score(query, doc["display_name"])
        preferred_hit = doc["display_name"] == preferred_name
        if preferred_hit:
            label = max(label, 1.0)
        if bm25_norm[idx] <= 0 and vector_norm[idx] <= 0 and label <= 0:
            continue
        branch = "both" if idx in intersection_ids else ("bm25_only" if idx in bm25_top else "vector_only")
        rank_score = HYBRID_BM25_WEIGHT * bm25_norm[idx] + HYBRID_VECTOR_WEIGHT * vector_norm[idx] + 0.25 * label
        if preferred_hit:
            branch = "preferred_alias"
            rank_score += 0.45
        if branch == "both":
            rank_score += 0.08
        elif branch == "bm25_only" and vector_raw[idx] < 0.12:
            rank_score *= 0.55

        vector_conf = max(0.0, min(1.0, vector_raw[idx] / 0.30))
        match_score = 0.50 * bm25_norm[idx] + 0.50 * vector_conf
        if preferred_hit:
            match_score = max(match_score, 0.90)
        if branch == "both":
            match_score = min(1.0, match_score + 0.08)
        elif branch == "bm25_only" and vector_raw[idx] < 0.12:
            match_score *= 0.70
        elif branch == "vector_only" and bm25_norm[idx] == 0 and vector_raw[idx] < 0.16:
            match_score *= 0.85

        rows.append({
            "slot_id": doc["symptom_id"],
            "display_text": doc["display_name"],
            "score": round(float(match_score), 4),
            "rank_score": round(float(rank_score), 4),
            "bm25_score": round(float(bm25_norm[idx]), 4),
            "vector_score": round(float(vector_raw[idx]), 4),
            "vector_norm": round(float(vector_norm[idx]), 4),
            "label_score": round(float(label), 4),
            "retrieval_branch": branch,
            "source": "diseases_cleaned+symptom_index",
            "evidence": doc.get("evidence", [])[:3],
            "linked_disease_names": doc.get("linked_disease_names", [])[:8],
            "domain_candidates": doc.get("domain_candidates", []),
            "vector_error": vector_error,
        })

    rows.sort(key=lambda item: item["rank_score"], reverse=True)
    return rows[:HYBRID_TOP_K]


def is_hybrid_candidate_accepted(candidate):
    """Require vector-centered hybrid evidence before a symptom becomes confirmed.

    Alias/label text can boost ranking, but it cannot confirm a symptom by itself.
    With Titan enabled, at least one semantic signal plus one lexical/label signal
    must be present. Without Titan, BM25 and label evidence must both be present.
    """
    bm25 = float(candidate.get("bm25_score") or 0)
    vector = float(candidate.get("vector_score") or 0)
    label = float(candidate.get("label_score") or 0)
    if USE_TITAN_EMBEDDING:
        if vector >= HYBRID_MIN_VECTOR_SCORE and (bm25 >= HYBRID_MIN_BM25_SCORE or label >= HYBRID_MIN_LABEL_SCORE):
            return True, "vector_plus_lexical_or_label"
        return False, (
            "hybrid_gate_failed:"
            f" vector={vector}, bm25={bm25}, label={label}"
        )
    if bm25 >= HYBRID_MIN_BM25_SCORE and label >= HYBRID_MIN_LABEL_SCORE:
        return True, "bm25_plus_label_without_vector"
    return False, f"bm25_gate_failed: bm25={bm25}, label={label}"

def match_slots(body):
    """`POST /match` 진입점. LLM span을 원페이퍼에 표시할 matched_slots로 변환합니다."""
    spans = body.get("spans") or []
    matched = []
    unmatched = []
    for span in spans:
        slot_id = span.get("slot_ref") or "other"
        span_type = span.get("type", "symptom")
        if not is_symptom_like_span(span_type, slot_id):
            unmatched.append(span)
            continue
        candidates = retrieve_symptom_docs(
            span.get("source_quote", ""),
            span.get("normalized_text") or span.get("name") or "",
            span.get("name") or slot_to_name(slot_id),
            slot_id,
        )
        if not candidates:
            unmatched.append(span)
            continue
        top = candidates[0]
        score = Decimal(str(top.get("score", 0)))
        accepted, accept_reason = is_hybrid_candidate_accepted(top)
        if not accepted:
            rejected = dict(span)
            rejected["ir_rejected"] = True
            rejected["ir_reject_reason"] = accept_reason
            rejected["top_candidates"] = candidates[:3]
            unmatched.append(rejected)
            continue
        status = span.get("status") if span.get("status") in ("있음", "없음", "확인필요") else "있음"
        if status == "있음" and float(score) < HYBRID_ACCEPT_THRESHOLD:
            status = "확인필요"
        name = top.get("display_text") or span.get("name") or slot_to_name(top.get("slot_id"))
        alert = bool(
            span.get("alert")
            or top.get("slot_id") in ("hemoptysis", "dyspnea", "chest_pain")
            or name in IR_RED_FLAG_NAMES
        )
        matched.append({
            "slot_id": top.get("slot_id"),
            "name": name,
            "score": score,
            "source_quote": span.get("source_quote", ""),
            "span_type": span_type,
            "alert": alert,
            "normalized_text": span.get("normalized_text") or span.get("name") or name,
            "status": status,
            "explain": make_symptom_match_explain(span, top),
            "ir_method": "bm25_titan_hybrid" if USE_TITAN_EMBEDDING else "bm25_only",
            "ir_trace": {
                "query": normalize_text(" ".join([
                    span.get("source_quote", ""),
                    span.get("normalized_text") or span.get("name") or "",
                ])),
                "bm25_score": top.get("bm25_score"),
                "vector_score": top.get("vector_score"),
                "vector_norm": top.get("vector_norm"),
                "label_score": top.get("label_score"),
                "rank_score": top.get("rank_score"),
                "retrieval_branch": top.get("retrieval_branch"),
                "accept_reason": accept_reason,
                "source": top.get("source"),
                "linked_disease_names": top.get("linked_disease_names", []),
                "evidence": top.get("evidence", []),
                "top_candidates": [
                    {
                        "slot_id": cand.get("slot_id"),
                        "name": cand.get("display_text"),
                        "score": cand.get("score"),
                        "bm25_score": cand.get("bm25_score"),
                        "vector_score": cand.get("vector_score"),
                        "rank_score": cand.get("rank_score"),
                    }
                    for cand in candidates[:3]
                ],
            },
        })
    return {"matched_slots": matched, "unmatched_spans": unmatched}


def slot_to_name(slot_id):
    if slot_id:
        indexed_name = get_symptom_name_by_id(slot_id)
        if indexed_name:
            return indexed_name
    mapping = {slot_id: name for name, slot_id, _, _ in SYMPTOM_RULES}
    return mapping.get(slot_id, slot_id or "-")


def make_symptom_match_explain(span, top):
    branch = top.get("retrieval_branch") or "hybrid"
    bm25_score = top.get("bm25_score", 0)
    vector_score = top.get("vector_score", 0)
    label_score = top.get("label_score", 0)
    if branch == "safety_alias_override":
        return "안전 관련 핵심 표현이 있어 표준 증상 후보를 우선 매칭했습니다."
    return (
        "환자 표현을 아산백과 기반 증상 인덱스와 비교했습니다. "
        f"BM25 {bm25_score}, Titan 의미점수 {vector_score}, 표준명 유사도 {label_score}를 함께 반영했습니다."
    )
