"""문진 extraction 전에 붙이는 경량 RAG 컨텍스트.

이 모듈은 환자 발화에서 증상을 직접 추출하지 않습니다. LLM이 표준화와
의미 분할을 할 때 참고할 수 있도록, 이미 보유한 원천 JSON 기반 증상 문서와
제한된 alias bridge에서 관련 문구를 검색해 prompt context로 제공합니다.

중요 원칙:
- RAG 결과는 "참고 근거"일 뿐 최종 추출값이 아닙니다.
- source_quote는 여전히 환자 원문에서만 나와야 합니다.
- 증상 매칭의 최종 결정은 뒤 단계의 Hybrid IR이 수행합니다.
"""

from __future__ import annotations

import re
from typing import Any

from clinical_terms import IR_TEXT_ALIASES, SYMPTOM_RULES
from domain_config import excluded_ir_symptom_names, selected_domain_pack_id
from retrieval_documents import get_ir_index
from settings import DATA_DIR, DISEASES_PATH, SYMPTOM_INDEX_PATH
from utils import clean_quote, normalize_text


EXCLUDED_IR_SYMPTOM_NAMES = excluded_ir_symptom_names()

ALIAS_ACTIVE_BOOST = 35.0
ALIAS_INACTIVE_PENALTY = 0.2

INACTIVE_CONTEXT_PATTERNS = [
    r"(없(?!던)|없는|없어|없었|안\s*(?:나|보|해|들|아프|차|쉬)|않|아니|아녀|아닌|진\s*않|지는\s*않)",
    r"(나아|나았|괜찮아졌|줄었|내렸|호전)",
]
ACTIVE_ABSENCE_SYMPTOMS = {"식욕부진", "기운없음"}
ACTIVE_NEGATION_CONTEXT_PATTERNS = {
    "감기 증상": [r"감기\s*기운|개운(?:하지|치)\s*않"],
    "근력 약화": [r"힘이\s*잘\s*안\s*들어|팔다리.{0,8}힘"],
    "목소리 변화": [r"(?:목소리|소리).{0,14}안\s*나(?:오|와)"],
    "부정맥": [r"맥.{0,10}고르지|고르지\s*않"],
    "재채기": [r"재채기.{0,12}멈추질\s*않"],
    "삼키기 곤란": [r"(?:삼키|목에\s*걸린|음식|약|밥).{0,24}안\s*넘어"],
}
INACTIVE_OVERRIDE_CONTEXT_PATTERNS = {
    "삼키기 곤란": [r"안\s*넘어가(?:는\s*정도는\s*아니|진\s*않|지는\s*않|지\s*않)"],
}
SEMANTIC_INACTIVE_PATTERNS = [
    ("삼키기 곤란", r"(?:음식|약|밥).{0,20}안\s*넘어가(?:는\s*정도는\s*아니|진\s*않|지는\s*않|지\s*않)"),
    ("흉통", r"가[슴심].{0,28}아(?:픈|프|파|퍼).{0,10}(?:없|아니|아녀|않|괜찮아졌)"),
    ("목의 통증", r"목.{0,20}아(?:픈|프|파|퍼).{0,10}(?:없|아니|아녀|않|괜찮아졌)"),
    ("복부 통증", r"배.{0,28}아(?:픈|프|파|퍼).{0,10}(?:없|아니|아녀|않|괜찮아졌)"),
    ("객혈", r"피(?:는|가)?\s*안\s*(?:보|나)|피(?:는|가)?\s*없"),
    ("설사", r"설사.{0,6}안\s*해"),
]


def rag_source_files() -> list[str]:
    """현재 배포 패키지에 맞는 RAG 참조 출처를 trace에 남깁니다."""
    if DISEASES_PATH.exists() and SYMPTOM_INDEX_PATH.exists():
        return [_source_label(DISEASES_PATH), _source_label(SYMPTOM_INDEX_PATH), "clinical_terms.IR_TEXT_ALIASES"]
    return [f"domain_packs/{selected_domain_pack_id()}.json", "clinical_terms.IR_TEXT_ALIASES"]


def _source_label(path) -> str:
    try:
        return str(path.relative_to(DATA_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def retrieve_intake_rag_context(
    transcript: str,
    question_type: str | None = None,
    top_k: int = 4,
) -> dict[str, Any]:
    """환자 발화와 가까운 표준 증상 문서와 구어체 힌트를 검색합니다."""
    query = normalize_text(transcript)
    if not query:
        return empty_rag_context()

    symptom_refs = retrieve_symptom_references(query, top_k=top_k)
    alias_hints = retrieve_alias_hints(query)
    context = {
        "retriever": "local_reference_rag",
        "source_files": rag_source_files(),
        "question_type": question_type or "",
        "query_chars": len(query),
        "alias_hints": alias_hints,
        "symptom_references": symptom_refs,
    }
    context["prompt_note"] = build_rag_prompt_note(context)
    return context


def empty_rag_context() -> dict[str, Any]:
    """검색할 원문이 없을 때도 trace 구조를 일정하게 유지합니다."""
    return {
        "retriever": "local_reference_rag",
        "source_files": rag_source_files(),
        "question_type": "",
        "query_chars": 0,
        "alias_hints": [],
        "symptom_references": [],
        "prompt_note": "",
    }


def retrieve_symptom_references(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """BM25로 원천 JSON 기반 증상 문서 중 관련 후보를 가져옵니다."""
    docs, bm25 = get_ir_index()
    scores = bm25.scores(query)
    alias_matches = best_alias_matches_by_name(query)
    ranked = sorted(
        enumerate(scores),
        key=lambda item: reference_rank_score(item[1], alias_matches.get(docs[item[0]].get("display_name"))),
        reverse=True,
    )
    refs: list[dict[str, Any]] = []
    for idx, score in ranked:
        if len(refs) >= max(0, top_k):
            break
        alias_match = alias_matches.get(docs[idx].get("display_name"))
        if alias_match and alias_match.get("polarity") == "inactive_or_negated":
            continue
        rank_score = reference_rank_score(score, alias_match)
        if score <= 0:
            if not alias_match or alias_match.get("polarity") != "active_or_context":
                continue
        if rank_score <= 0:
            continue
        doc = docs[idx]
        if doc.get("display_name") in EXCLUDED_IR_SYMPTOM_NAMES:
            continue
        refs.append(
            {
                "symptom_id": doc.get("symptom_id"),
                "display_name": doc.get("display_name"),
                "bm25_score": round(float(score), 4),
                "rank_score": round(float(rank_score), 4),
                "alias_match": alias_match or {},
                "departments": doc.get("departments", [])[:3],
                "evidence": [
                    {
                        "disease_name": item.get("disease_name"),
                        "section": item.get("section"),
                        "text": item.get("text"),
                    }
                    for item in (doc.get("evidence") or [])[:2]
                ],
            }
        )
    return refs


def retrieve_alias_hints(query: str) -> list[dict[str, str]]:
    """표준명/alias bridge에서 환자 표현과 직접 닿는 힌트를 찾습니다."""
    hints = []
    seen: set[tuple[str, str]] = set()
    for pattern, canonical_name in IR_TEXT_ALIASES:
        match = re.search(pattern, query)
        if not match:
            continue
        polarity = classify_alias_polarity(query, match, canonical_name)
        seen.add((canonical_name, clean_quote(match.group(0))))
        hints.append(
            {
                "matched_text": clean_quote(match.group(0)),
                "canonical_hint": canonical_name,
                "pattern": pattern,
                "polarity": polarity,
                "match_context": alias_match_context(query, match),
            }
        )
    for item in best_alias_matches_by_name(query).values():
        pattern = item.get("pattern") or ""
        key = (item.get("canonical_hint") or "", item.get("matched_text") or "")
        if key in seen or not pattern.startswith(("keyword:", "semantic_inactive:")):
            continue
        hints.append(item)
    hints.sort(key=alias_priority, reverse=True)
    return hints[:5]


def best_alias_matches_by_name(query: str) -> dict[str, dict[str, str]]:
    """각 표준 증상명별 가장 유용한 alias match를 찾습니다."""
    best: dict[str, dict[str, str]] = {}
    for pattern, canonical_name in IR_TEXT_ALIASES:
        for match in re.finditer(pattern, query):
            polarity = classify_alias_polarity(query, match, canonical_name)
            item = {
                "matched_text": clean_quote(match.group(0)),
                "canonical_hint": canonical_name,
                "pattern": pattern,
                "polarity": polarity,
                "match_context": alias_match_context(query, match),
            }
            current = best.get(canonical_name)
            if not current or alias_priority(item) > alias_priority(current):
                best[canonical_name] = item
    add_inactive_keyword_matches(query, best)
    add_semantic_inactive_matches(query, best)
    return best


def add_inactive_keyword_matches(query: str, best: dict[str, dict[str, str]]) -> None:
    """Alias가 놓친 명시적 부정/호전 keyword를 penalty 근거로 추가합니다.

    이 함수는 active boost를 만들지 않습니다. 예를 들어 `열은 없어`, `기침은
    안 나와`처럼 증상명이 부정 문맥에만 등장할 때 해당 후보를 낮추기 위한
    inactive marker만 보강합니다.
    """
    for canonical_name, _slot_id, keywords, _alert in SYMPTOM_RULES:
        for keyword in [canonical_name, *keywords]:
            keyword = clean_quote(keyword)
            if len(keyword) < 2:
                continue
            for match in re.finditer(re.escape(keyword), query):
                polarity = classify_alias_polarity(query, match, canonical_name)
                if polarity != "inactive_or_negated":
                    continue
                item = {
                    "matched_text": clean_quote(match.group(0)),
                    "canonical_hint": canonical_name,
                    "pattern": f"keyword:{keyword}",
                    "polarity": polarity,
                    "match_context": alias_match_context(query, match),
                }
                current = best.get(canonical_name)
                if not current or alias_priority(item) > alias_priority(current):
                    best[canonical_name] = item


def add_semantic_inactive_matches(query: str, best: dict[str, dict[str, str]]) -> None:
    """부위와 부정 표현이 떨어진 케이스를 inactive marker로 보강합니다."""
    for canonical_name, pattern in SEMANTIC_INACTIVE_PATTERNS:
        for match in re.finditer(pattern, query):
            item = {
                "matched_text": clean_quote(match.group(0)),
                "canonical_hint": canonical_name,
                "pattern": f"semantic_inactive:{pattern}",
                "polarity": "inactive_or_negated",
                "match_context": alias_match_context(query, match, before=0, after=0),
            }
            current = best.get(canonical_name)
            if not current or current.get("polarity") != "active_or_context":
                best[canonical_name] = item


def alias_priority(item: dict[str, str]) -> tuple[int, int]:
    """active alias를 inactive alias보다 우선하고, 긴 match를 더 강한 근거로 봅니다."""
    polarity_score = 1 if item.get("polarity") == "active_or_context" else 0
    return polarity_score, len(item.get("matched_text") or "")


def reference_rank_score(bm25_score: float, alias_match: dict[str, str] | None = None) -> float:
    """RAG reference ranking score.

    BM25는 부정과 호전 맥락을 이해하지 못하므로 alias match가 있으면 보정합니다.
    active alias는 짧은 핵심 증상어가 top 후보에서 밀리지 않게 올리고, inactive
    alias는 후보에 남기더라도 순위를 낮춥니다.
    """
    score = float(bm25_score or 0)
    if not alias_match:
        return score
    if alias_match.get("polarity") == "inactive_or_negated":
        return score * ALIAS_INACTIVE_PENALTY
    return score + ALIAS_ACTIVE_BOOST


def classify_alias_polarity(query: str, match: re.Match, canonical_name: str = "") -> str:
    """Alias가 부정/호전 문맥인지 가볍게 판정합니다."""
    context = alias_polarity_context(query, match)
    if canonical_name in ACTIVE_ABSENCE_SYMPTOMS and "없" in match.group(0):
        return "active_or_context"
    if any(re.search(pattern, context) for pattern in INACTIVE_OVERRIDE_CONTEXT_PATTERNS.get(canonical_name, [])):
        return "inactive_or_negated"
    if any(re.search(pattern, context) for pattern in ACTIVE_NEGATION_CONTEXT_PATTERNS.get(canonical_name, [])):
        return "active_or_context"
    if any(re.search(pattern, context) for pattern in INACTIVE_CONTEXT_PATTERNS):
        return "inactive_or_negated"
    return "active_or_context"


def alias_match_context(query: str, match: re.Match, before: int = 6, after: int = 18) -> str:
    start = max(0, match.start() - before)
    end = min(len(query), match.end() + after)
    return clean_quote(query[start:end])


def alias_polarity_context(query: str, match: re.Match) -> str:
    """부정/호전 판정에 쓰는 같은 문절 중심 context입니다.

    `열은 나는데 춥지는 않아`처럼 한 문장에 여러 의미가 섞이면 전체 window를
    보면 앞 증상까지 부정으로 오염됩니다. match 이후를 짧게 보되 `는데`,
    `지만`, 쉼표 같은 문절 경계 뒤는 잘라내고, match 바로 앞의 `안` 정도만
    함께 봅니다.
    """
    before = query[max(0, match.start() - 3):match.start()]
    after = query[match.end():min(len(query), match.end() + 22)]
    boundary_match = re.search(r"^데|는데|[가-힣]데|지만|고\s|,|\.|\?|!", after)
    if boundary_match:
        after = after[:boundary_match.start()]
    return clean_quote(before + match.group(0) + after)


def build_rag_prompt_note(context: dict[str, Any]) -> str:
    """LLM prompt에 넣을 짧은 RAG 참고 문단을 만듭니다."""
    alias_hints = context.get("alias_hints") or []
    symptom_refs = context.get("symptom_references") or []
    if not alias_hints and not symptom_refs:
        return ""

    lines = [
        "Retrieved reference context for normalization. Use this only as weak context, not as patient facts.",
        "The patient transcript remains the only source for source_quote/original_quote.",
        "Do not add symptoms, diagnoses, tests, or medications just because they appear below.",
    ]
    if alias_hints:
        lines.append("Colloquial/alias hints:")
        for item in alias_hints:
            polarity = item.get("polarity") or "active_or_context"
            if polarity == "inactive_or_negated":
                lines.append(
                    f"- '{item.get('matched_text')}' may align with '{item.get('canonical_hint')}', "
                    "but it appears in a negated or improved context. Do not treat it as current unless the transcript says it is active."
                )
            else:
                lines.append(f"- '{item.get('matched_text')}' may align with standard wording '{item.get('canonical_hint')}'.")
    if symptom_refs:
        lines.append("Nearby symptom reference documents from source JSON:")
        for item in symptom_refs:
            evidence_text = "; ".join(
                clean_quote(evidence.get("text"))
                for evidence in item.get("evidence", [])
                if clean_quote(evidence.get("text"))
            )
            if evidence_text:
                lines.append(f"- {item.get('display_name')}: {evidence_text}")
            else:
                lines.append(f"- {item.get('display_name')}")
    return "\n".join(lines)
