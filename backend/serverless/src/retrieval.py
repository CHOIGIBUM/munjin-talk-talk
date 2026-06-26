"""Symptom retrieval and scoring.

LLM이 추출한 symptom span을 그대로 믿지 않고, Asan-derived source JSON에서 만든
증상 문서를 대상으로 BM25 lexical score, Titan embedding vector score, label/alias
hint를 조합해 표준 증상명으로 매칭합니다.
"""

import re
from decimal import Decimal

from clinical_state import is_non_active_symptom_state
from clinical_terms import (
    ALERT_SLOT_IDS,
    IR_SLOT_TO_CANONICAL_NAME,
    IR_RED_FLAG_NAMES,
    SYMPTOM_RULES,
    find_symptom_quote,
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
)
from domain_config import excluded_ir_symptom_names
from retrieval_documents import get_ir_index, get_symptom_name_by_id, preferred_canonical_name
from retrieval_embeddings import embed_text, get_doc_embeddings
from retrieval_scoring import cosine, direct_label_score, minmax_norm
from utils import (
    normalize_text,
)


EXCLUDED_IR_SYMPTOM_NAMES = excluded_ir_symptom_names()
CO_OCCURRING_RESCUE_SLOT_IDS = {
    "chest_discomfort",
    "dyspnea",
    "leg_edema",
    "throat_irritation",
}

# LLM이 검색 힌트로 쓸 수는 있지만, IR query에 붙이면 오히려 검색을 흐리는 표현입니다.
# 예를 들어 "목이 칼칼하다 + 불편함"보다 "목이 칼칼하다"만 검색하는 편이 안정적입니다.
GENERIC_SYMPTOM_HINTS = {
    "불편",
    "불편함",
    "불편 증상",
    "증상",
    "증세",
    "문제",
    "이상",
    "느낌",
    "몸살",
    "몸살 느낌",
    "일반적인 불편함",
    "환자 질문",
    "통증",
    "아픔",
}
GENERIC_SYMPTOM_HINT_PATTERNS = [
    r"^(일반적인\s*)?불편(함|감| 증상)?$",
    r"^(증상|증세|문제|이상|느낌)$",
    r"^몸살(\s*느낌)?$",
    r"^환자\s*질문$",
    r"^(통증|아픔)$",
]

IR_QUERY_NOISE_PATTERNS = [
    r"\[[^\]]+\]",
    r"\b(환자|보호자|딸|아들|배우자)\b",
    r"(의사에게|선생님께|추가로|따로|궁금한|궁금합니다|질문|문의|여쭤보고|싶습니다|싶어요)",
]


def retrieve_symptom_docs(source_quote, normalized_text, span_name="", preferred_slot_id=""):
    """하나의 symptom span에 대해 BM25/vector/label 후보를 모아 상위 증상을 반환합니다."""
    docs, bm25 = get_ir_index()
    preferred_name = preferred_canonical_name(preferred_slot_id, span_name, normalized_text, source_quote)
    slot_name = slot_to_name(preferred_slot_id) if preferred_slot_id else ""
    query_slot_id = preferred_slot_id if preferred_name in ("", slot_name) else ""
    query = build_symptom_query(
        source_quote,
        normalized_text,
        preferred_name or span_name,
        query_slot_id,
    )
    if not query:
        return []

    bm25_raw = bm25.scores(query)
    bm25_norm = minmax_norm(bm25_raw)
    q_emb = None
    vector_raw = [0.0] * len(docs)
    vector_error = ""
    try:
        q_emb = embed_text(query)
    except Exception as exc:
        # 운영 trace에는 원문 예외 메시지를 남기지 않는다.
        # AWS/라이브러리 예외에는 요청 본문 일부가 섞일 수 있어 타입만 보존한다.
        vector_error = f"embedding_exception:{exc.__class__.__name__}"

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
        # 배포 패키지에 사전 계산 vector index가 없으면 BM25/label 후보만 대상으로
        # Titan embedding을 즉시 계산해 semantic 비교를 이어갑니다.
        for idx in list(candidate_ids):
            try:
                emb = embed_text(docs[idx].get("embedding_text", ""))
                vector_raw[idx] = max(0.0, cosine(q_emb, emb))
            except Exception as exc:
                # 재시도 실패도 같은 정책으로 예외 타입만 남긴다.
                vector_error = f"embedding_retry_exception:{exc.__class__.__name__}"
        candidate_vectors = [vector_raw[idx] for idx in candidate_ids]
        norm_lookup = dict(zip(candidate_ids, minmax_norm(candidate_vectors)))
        vector_norm = [norm_lookup.get(idx, 0.0) for idx in range(len(docs))]

    rows = []
    intersection_ids = bm25_top & (vector_top or candidate_ids)
    for idx in candidate_ids:
        doc = docs[idx]
        if doc["display_name"] in EXCLUDED_IR_SYMPTOM_NAMES:
            # 인덱스/embedding hash는 유지하고, 운영 후보 채택에서만 제외합니다.
            continue
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
            rank_score += 1.0
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
            "source": doc.get("source", "diseases_cleaned+symptom_index"),
            "evidence": doc.get("evidence", [])[:3],
            "linked_disease_names": doc.get("linked_disease_names", [])[:8],
            "domain_candidates": doc.get("domain_candidates", []),
            "vector_error": vector_error,
        })

    rows.sort(key=lambda item: item["rank_score"], reverse=True)
    return rows[:HYBRID_TOP_K]


LOCAL_NASAL_OBSTRUCTION_PATTERN = re.compile(
    r"(코\s*(가|는|도)?\s*.{0,8}(막|답답)|코막힘|코\s*막힘)"
)
LOCAL_BREATHING_CONSEQUENCE_PATTERN = re.compile(
    r"(숨\s*쉬기|숨쉬기|숨\s*쉬는|숨쉬는).{0,12}(힘|불편|어렵)"
)
INDEPENDENT_DYSPNEA_PATTERN = re.compile(
    r"(숨이\s*차|숨차|호흡\s*곤란|가슴.{0,8}답답|흉부.{0,8}답답|말하기.{0,8}힘)"
)
AGENDA_ONLY_CONCERN_PATTERN = re.compile(r"(걱정|걱정돼|걱정되|궁금|문의|물어)")
ANXIETY_SYMPTOM_PATTERN = re.compile(r"(불안|초조|공포|패닉|안절부절|잠.{0,4}못)")
NAUSEA_OR_VOMIT_PATTERN = re.compile(r"(속.{0,6}울렁|메스꺼|토했|구토|토할)")
ABDOMINAL_PAIN_MARKER_PATTERN = re.compile(r"(복통|배.{0,8}아프|배.{0,8}통증|복부.{0,8}통증|창지.{0,8}꼬)")
BLOATING_MARKER_PATTERN = re.compile(r"(더부룩|빵빵|부풀|팽만|가스)")


def looks_like_local_nasal_obstruction(*texts):
    """Return True when breathing difficulty is explained by local nasal blockage."""
    joined = normalize_text(" ".join(str(text or "") for text in texts))
    if not joined:
        return False
    return bool(
        LOCAL_NASAL_OBSTRUCTION_PATTERN.search(joined)
        and LOCAL_BREATHING_CONSEQUENCE_PATTERN.search(joined)
        and not INDEPENDENT_DYSPNEA_PATTERN.search(joined)
    )


def apply_local_obstruction_guard(candidates, span):
    """Prefer nasal obstruction over dyspnea when the quote says the nose is blocked."""
    if not candidates:
        return candidates
    source_quote = span.get("source_quote", "")
    normalized = span.get("normalized_text") or span.get("name") or ""
    if not looks_like_local_nasal_obstruction(source_quote, normalized):
        return candidates
    if not is_dyspnea_candidate_context(candidates, span):
        return candidates

    guarded = []
    nasal_candidate = None
    for candidate in candidates:
        slot_id = candidate.get("slot_id")
        name = candidate.get("display_text") or ""
        if slot_id == "nasal_obstruction" or name == "코막힘":
            nasal_candidate = dict(candidate)
            continue
        if slot_id == "dyspnea" or name == "호흡곤란":
            continue
        guarded.append(candidate)

    if nasal_candidate is None:
        rescue_candidates = retrieve_symptom_docs(
            source_quote,
            "코막힘",
            "코막힘",
            "nasal_obstruction",
        )
        nasal_candidate = next(
            (
                dict(candidate)
                for candidate in rescue_candidates
                if candidate.get("slot_id") == "nasal_obstruction"
                or candidate.get("display_text") == "코막힘"
            ),
            None,
        )
        if nasal_candidate is None:
            return guarded

    nasal_candidate["score"] = max(float(nasal_candidate.get("score") or 0), 0.9)
    nasal_candidate["rank_score"] = max(float(nasal_candidate.get("rank_score") or 0), 2.0)
    nasal_candidate["label_score"] = max(float(nasal_candidate.get("label_score") or 0), 1.0)
    nasal_candidate["retrieval_branch"] = "local_obstruction_guard"
    return [nasal_candidate] + guarded


def is_dyspnea_candidate_context(candidates, span):
    top = candidates[0] if candidates else {}
    text = normalize_text(" ".join([
        span.get("name", ""),
        span.get("normalized_text", ""),
    ]))
    return bool(
        top.get("slot_id") == "dyspnea"
        or top.get("display_text") == "호흡곤란"
        or span.get("slot_ref") == "dyspnea"
        or "호흡곤란" in text
    )


def is_ir_noise_span(span):
    """Filter agenda-only or over-read spans before symptom IR."""
    return is_agenda_only_anxiety_span(span) or is_non_specific_gi_overread_span(span)


def is_agenda_only_anxiety_span(span):
    slot_id = str(span.get("slot_ref") or "")
    if slot_id != "anxiety":
        return False
    text = normalize_text(" ".join([
        span.get("source_quote", ""),
        span.get("normalized_text", ""),
    ]))
    if not text:
        return False
    return bool(
        AGENDA_ONLY_CONCERN_PATTERN.search(text)
        and not ANXIETY_SYMPTOM_PATTERN.search(text)
    )


def is_non_specific_gi_overread_span(span):
    slot_id = str(span.get("slot_ref") or "")
    if slot_id not in {"abdominal_pain", "abdominal_bloating"}:
        return False
    text = normalize_text(" ".join([
        span.get("source_quote", ""),
        span.get("normalized_text", ""),
    ]))
    if not NAUSEA_OR_VOMIT_PATTERN.search(text):
        return False
    if slot_id == "abdominal_pain":
        return not ABDOMINAL_PAIN_MARKER_PATTERN.search(text)
    return not BLOATING_MARKER_PATTERN.search(text)


def is_hybrid_candidate_accepted(candidate):
    """표준 증상 확정에는 Titan 의미 신호와 lexical/label 근거가 함께 필요합니다."""
    bm25 = float(candidate.get("bm25_score") or 0)
    vector = float(candidate.get("vector_score") or 0)
    label = float(candidate.get("label_score") or 0)
    branch = candidate.get("retrieval_branch") or ""
    score = float(candidate.get("score") or 0)
    if branch == "preferred_alias" and label >= 1.0 and score >= 0.9:
        return True, "preferred_slot_or_label"
    if branch == "local_obstruction_guard" and score >= 0.9:
        return True, "local_obstruction_guard"
    if vector >= HYBRID_MIN_VECTOR_SCORE and (bm25 >= HYBRID_MIN_BM25_SCORE or label >= HYBRID_MIN_LABEL_SCORE):
        return True, "vector_plus_lexical_or_label"
    return False, (
        "hybrid_gate_failed:"
        f" vector={vector}, bm25={bm25}, label={label}"
    )

def match_slots(body):
    """LangGraph 내부 IR 단계. LLM span을 원페이퍼에 표시할 matched_slots로 변환합니다."""
    spans = body.get("spans") or []
    matched = []
    unmatched = []
    for span in spans:
        slot_id = span.get("slot_ref") or "other"
        span_type = span.get("type", "symptom")
        if not has_ir_eligible_symptom_span(span):
            unmatched.append(span)
            continue
        candidates = retrieve_symptom_docs(
            span.get("source_quote", ""),
            span.get("normalized_text") or span.get("name") or "",
            span.get("name") or slot_to_name(slot_id),
            slot_id,
        )
        candidates = apply_local_obstruction_guard(candidates, span)
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
            or top.get("slot_id") in ALERT_SLOT_IDS
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
            "ir_method": "bm25_titan_hybrid",
            "ir_trace": {
                "query": build_symptom_query(
                    span.get("source_quote", ""),
                    "코막힘"
                    if top.get("retrieval_branch") == "local_obstruction_guard"
                    else span.get("normalized_text") or span.get("name") or "",
                    "코막힘"
                    if top.get("retrieval_branch") == "local_obstruction_guard"
                    else top.get("display_text") or span.get("name") or slot_to_name(slot_id),
                    "nasal_obstruction"
                    if top.get("retrieval_branch") == "local_obstruction_guard"
                    else top.get("slot_id") or slot_id,
                ),
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
    matched = add_cooccurring_symptom_matches(matched, spans)
    return {"matched_slots": dedupe_matched_slots(matched), "unmatched_spans": unmatched}


def add_cooccurring_symptom_matches(matched, spans):
    """Recover a second active symptom when one LLM span contains two clear symptoms."""
    matched_ids = {item.get("slot_id") for item in matched}
    recovered = list(matched)
    for span in spans:
        if not isinstance(span, dict):
            continue
        if should_skip_active_symptom_ir(span) or is_ir_noise_span(span):
            continue
        text = normalize_text(span.get("source_quote") or span.get("normalized_text") or "")
        if not text:
            continue
        for name, slot_id, keywords, _alert in SYMPTOM_RULES:
            if slot_id not in CO_OCCURRING_RESCUE_SLOT_IDS or slot_id in matched_ids:
                continue
            quote = find_symptom_quote(text, slot_id, keywords)
            if not quote or quote_looks_non_active(text, quote):
                continue
            if not cooccurring_quote_allowed(slot_id, text, quote):
                continue
            candidates = retrieve_symptom_docs(quote, name, name, slot_id)
            if not candidates:
                continue
            top = candidates[0]
            accepted, accept_reason = is_hybrid_candidate_accepted(top)
            if not accepted or top.get("slot_id") != slot_id:
                continue
            recovered.append(make_matched_slot_from_candidate(span, top, quote, accept_reason))
            matched_ids.add(slot_id)
    return recovered


def make_matched_slot_from_candidate(span, top, quote, accept_reason):
    score = Decimal(str(top.get("score", 0)))
    name = top.get("display_text") or slot_to_name(top.get("slot_id"))
    return {
        "slot_id": top.get("slot_id"),
        "name": name,
        "score": score,
        "source_quote": quote,
        "span_type": "symptom",
        "alert": bool(top.get("slot_id") in ALERT_SLOT_IDS or name in IR_RED_FLAG_NAMES),
        "normalized_text": name,
        "status": "있음",
        "explain": make_symptom_match_explain(span, top),
        "ir_method": "bm25_titan_hybrid",
        "ir_trace": {
            "query": build_symptom_query(quote, name, name, top.get("slot_id")),
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
                for cand in candidates_from_top(top)
            ],
        },
    }


def candidates_from_top(top):
    return [top] if top else []


def quote_looks_non_active(text, quote):
    window = symptom_quote_context_window(text, quote)
    return bool(
        re.search(r"(없|없어|없었|전혀|아니|않|안\s*나|나지\s*않)", window)
        or re.search(r"(나아|호전|덜|줄어|사라|해소|내렸)", window)
    )


def cooccurring_quote_allowed(slot_id, text, quote):
    target = normalize_text(" ".join([text, quote]))
    if slot_id == "chest_discomfort":
        return bool(re.search(r"(가슴|흉부|명치).{0,10}(답답|불편|압박)", target))
    if slot_id == "dyspnea":
        if looks_like_local_nasal_obstruction(text):
            return False
        return bool(re.search(r"(숨\s*쉬기|숨쉬기|숨이|호흡).{0,12}(힘|어렵|불편|차)", target))
    if slot_id == "leg_edema":
        return bool(re.search(r"(다리|발|발목|하지).{0,10}(붓|부종|퉁퉁)", target))
    if slot_id == "throat_irritation":
        return bool(re.search(r"(목|목구멍).{0,10}(아프|따갑|칼칼|쓰리)", target))
    return False


def symptom_quote_context_window(text, quote, radius=12):
    text = normalize_text(text)
    quote = normalize_text(quote)
    if not text or not quote:
        return ""
    idx = text.find(quote)
    if idx < 0:
        return text
    start = max(0, idx - radius)
    end = min(len(text), idx + len(quote) + radius)
    return text[start:end]


def dedupe_matched_slots(matched):
    deduped = []
    seen = set()
    for item in matched:
        slot_id = item.get("slot_id")
        if not slot_id or slot_id in seen:
            continue
        seen.add(slot_id)
        deduped.append(item)
    return deduped


def should_skip_active_symptom_ir(span):
    """호전/부재로 검증된 span은 현재 불편함 카드용 IR에서 제외합니다.

    LLM이 "열은 내렸다", "두통은 없어졌다", "지금 열은 없다"처럼
    호전/부재 맥락을 `progress_improved`, `symptom_absent`, `status=없음`
    조합으로 태깅했다면, 해당 표현은 "오늘 말한 불편함" 카드로 올리지 않습니다.
    대신 answers artifact와 clinical_clues에서 재진 경과/현재 부재 단서로 확인합니다.
    """
    return is_non_active_symptom_state(span)


def has_ir_eligible_symptom_span(span):
    """현재 증상으로 태깅된 span이면 문항 종류와 무관하게 IR 대상으로 봅니다.

    Q3 복약 문항처럼 질문 의도는 복약 확인이어도 환자가 "약은 없고 숨이 차다"처럼
    현재 증상을 함께 말할 수 있습니다. 이때 question_type으로 먼저 거르면 실제 증상을
    놓치므로, span 자체가 active symptom인지 여부를 IR 실행 기준으로 사용합니다.
    """
    if not isinstance(span, dict):
        return False
    slot_id = span.get("slot_ref") or "other"
    span_type = span.get("type", "symptom")
    if should_skip_active_symptom_ir(span):
        return False
    if is_ir_noise_span(span):
        return False
    if is_symptom_like_span(span_type, slot_id):
        return True
    return is_context_symptom_rescue_span(span)


def is_context_symptom_rescue_span(span):
    """Rescue active context spans when their name/slot is an ontology symptom."""
    if not isinstance(span, dict):
        return False
    if str(span.get("type") or "") != "context":
        return False
    slot_id = str(span.get("slot_ref") or "")
    if slot_id and slot_id != "other" and slot_id in IR_SLOT_TO_CANONICAL_NAME:
        return True
    name = normalize_text(span.get("name") or span.get("normalized_text") or "")
    if not name or is_generic_symptom_hint(name):
        return False
    if preferred_canonical_name(slot_id, name):
        return True
    return any(
        normalize_text(canonical_name) == name
        for canonical_name in IR_SLOT_TO_CANONICAL_NAME.values()
    )


def build_symptom_query(source_quote, normalized_text, span_name="", preferred_slot_id=""):
    """IR query를 표준화 span과 LLM 증상 힌트 중심으로 구성합니다.

    IR 평가에서 원문 방언 quote까지 섞은 A안보다 `normalized_text + name`을 쓰는
    C안이 더 안정적이었습니다. 따라서 source_quote는 검증/trace에는 남기되,
    검색어에는 표준화된 의미와 LLM의 자연어 증상 힌트를 우선 사용합니다.
    표준화 결과가 비어 있는 예외 상황에서만 원문 quote를 보조 query로 사용합니다.
    """
    normalized = clean_ir_query_component(normalized_text)
    hint = clean_ir_query_component(span_name)
    slot_name = ""
    if preferred_slot_id and preferred_slot_id != "other":
        slot_name = clean_ir_query_component(slot_to_name(preferred_slot_id))
    narrowed_quote = narrow_source_quote_for_ir(
        source_quote,
        preferred_slot_id,
        hint,
        normalized,
    )

    parts = []
    for part in (slot_name, hint, narrowed_quote):
        if part and not is_generic_symptom_hint(part) and part not in parts:
            parts.append(part)
    if parts:
        return normalize_text(" ".join(parts))
    if normalized:
        return normalized
    return clean_ir_query_component(source_quote)


def narrow_source_quote_for_ir(source_quote, preferred_slot_id="", span_name="", normalized_text=""):
    """Keep only the symptom-sized quote when domain quote patterns can find one."""
    quote = clean_ir_query_component(source_quote)
    if not quote:
        return ""
    slot_id = str(preferred_slot_id or "")
    if slot_id and slot_id != "other":
        narrowed = find_symptom_quote(quote, slot_id, symptom_keywords_for_slot(slot_id))
        if narrowed:
            return clean_ir_query_component(narrowed)

    candidates = [
        clean_ir_query_component(span_name),
        clean_ir_query_component(normalized_text),
    ]
    for marker in candidates:
        if marker and marker in quote and not is_generic_symptom_hint(marker):
            return marker
    return ""


def symptom_keywords_for_slot(slot_id):
    """Return domain rule keywords for a symptom slot."""
    slot_id = str(slot_id or "")
    for _name, rule_slot_id, keywords, _alert in SYMPTOM_RULES:
        if rule_slot_id == slot_id:
            return keywords
    return []


def clean_ir_query_component(value):
    """IR 검색에 방해되는 speaker/meta 표현만 제거합니다.

    증상 단어 자체를 새로 만들거나 alias를 추가하지 않습니다. 환자/보호자 표식,
    "궁금합니다" 같은 agenda 표현처럼 검색 의도를 흐리는 주변 말만 걷어내어
    BM25와 vector가 실제 증상 표현에 더 집중하도록 합니다.
    """
    text = normalize_text(value or "")
    if not text:
        return ""
    for pattern in IR_QUERY_NOISE_PATTERNS:
        text = re.sub(pattern, " ", text)
    return normalize_text(text)


def is_generic_symptom_hint(span_name):
    """IR query에 붙이면 검색 품질을 떨어뜨리는 너무 일반적인 LLM hint인지 판단합니다.

    이 함수는 증상 정답을 새로 추정하지 않습니다. 단지 "불편함", "증상",
    "몸살 느낌"처럼 거의 모든 후보에 붙을 수 있는 단어를 query 확장에 쓰지 않도록
    막는 필터입니다. 구체 판단은 이후 BM25/vector와 linker가 담당합니다.
    """
    hint = normalize_text(span_name or "")
    if not hint:
        return True
    if hint in GENERIC_SYMPTOM_HINTS:
        return True
    if any(re.fullmatch(pattern, hint) for pattern in GENERIC_SYMPTOM_HINT_PATTERNS):
        return True
    tokens = [token for token in re.split(r"[\s,/|]+", hint) if token]
    return bool(tokens) and all(token in GENERIC_SYMPTOM_HINTS for token in tokens)


def slot_to_name(slot_id):
    if slot_id:
        indexed_name = get_symptom_name_by_id(slot_id)
        if indexed_name:
            return indexed_name
    mapping = {slot_id: name for name, slot_id, _, _ in SYMPTOM_RULES}
    return mapping.get(slot_id, slot_id or "-")


def make_symptom_match_explain(span, top):
    branch = top.get("retrieval_branch") or "hybrid"
    if branch == "safety_alias_override":
        return "안전 관련 핵심 표현이 있어 표준 증상 후보를 우선 매칭했습니다."
    if branch == "local_obstruction_guard":
        return "코막힘 때문에 숨쉬기 불편하다고 해석되어 호흡곤란 대신 코막힘으로 매칭했습니다."
    return (
        "환자 표현을 아산백과 기반 증상 인덱스와 비교했고, "
        "어휘 근거와 Titan 의미 벡터 근거가 함께 충족되어 표준 증상으로 매칭했습니다."
    )
