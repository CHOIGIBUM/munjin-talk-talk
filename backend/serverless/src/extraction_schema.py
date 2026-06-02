"""Pydantic-backed validation for LLM extraction output.

이 파일은 extraction.py가 호출하는 얇은 adapter입니다. 실제 fixed schema는
`schemas/extraction.py`에 있고, 여기서는 question_id 같은 런타임 기본값만 보강한
뒤 Pydantic 검증 결과를 기존 파이프라인 형식으로 돌려줍니다.
"""

from copy import deepcopy

from schemas.extraction import SymptomSlotRef, validate_extraction_payload


SYMPTOM_SLOT_REFS = set(SymptomSlotRef.__args__)
NON_SYMPTOM_SPAN_TYPES = {"medication", "medication_denial", "adherence_gap", "context"}


def normalize_extraction_output(obj, transcript, question_id, question_type=""):
    """LLM 출력이 fixed schema와 quote grounding을 통과하는지 검증합니다.

    반환 형식은 기존 retry loop와 맞추기 위해 `(normalized, errors)`입니다.
    errors가 비어 있지 않으면 extraction.py가 repair prompt를 만들어 LLM에 다시
    요청합니다.
    """
    prepared = prepare_extraction_payload(obj, question_id, question_type)
    normalized, errors = validate_extraction_payload(prepared, transcript)
    if errors:
        return {"spans": [], "structured": empty_structured(transcript)}, errors
    return normalized, []


def prepare_extraction_payload(obj, question_id, question_type=""):
    """LLM 출력에 런타임 기본값을 채워 Pydantic 검증 대상으로 만듭니다.

    이 단계는 의미 값을 창작하지 않습니다. source_quote, category, slot_ref,
    spans/structured 같은 핵심 필드가 없으면 그대로 검증 실패하게 둡니다.
    단, clinical clue의 source_question은 현재 문항 ID라는 런타임 문맥이므로
    누락된 경우에만 보강합니다.
    """
    payload = deepcopy(obj) if isinstance(obj, dict) else {}
    normalize_non_symptom_span_slots(payload, question_type)
    structured = payload.get("structured")
    if isinstance(structured, dict) and isinstance(structured.get("clinical_clues"), list):
        for clue in structured["clinical_clues"]:
            if isinstance(clue, dict):
                clue.setdefault("source_question", question_id)
    return payload


def normalize_non_symptom_span_slots(payload, question_type=""):
    """증상 IR 대상이 아닌 span의 slot_ref를 schema-safe 값으로 정리합니다.

    slot_ref는 Hybrid IR에서 증상 후보를 표준 증상명으로 맞추기 위한 필드입니다.
    Q3 초기 문항의 복약/무복약 답변이나 Q2 복약순응도 답변은 증상 검색 대상이
    아니므로 Nova가 `medication`, `none`, `supplement`처럼 자유롭게 쓴 값을
    그대로 두면 Pydantic enum에서 불필요하게 실패합니다.

    이 함수는 LLM이 추출한 source_quote, type, summary를 바꾸지 않고, 비증상
    span의 무관한 slot_ref만 `other`로 정규화합니다. 증상 문항의 symptom/new/
    progress span은 여전히 엄격한 enum 검증을 그대로 받습니다.
    """
    spans = payload.get("spans")
    if not isinstance(spans, list):
        return

    is_medication_question = question_type in {"current_medications", "adherence"}
    for span in spans:
        if not isinstance(span, dict):
            continue
        span_type = span.get("type")
        slot_ref = span.get("slot_ref")
        if span_type in NON_SYMPTOM_SPAN_TYPES or is_medication_question:
            span["slot_ref"] = "other"
        elif slot_ref not in SYMPTOM_SLOT_REFS:
            # 증상 span의 잘못된 slot_ref는 고치지 않습니다.
            # 그대로 실패해야 LLM repair loop가 다시 작동합니다.
            continue


def empty_structured(transcript):
    """검증 실패 시 DynamoDB에 잘못된 LLM 값을 저장하지 않기 위한 빈 구조입니다."""
    return {
        "standardized_text": transcript or "",
        "clinical_clues": [],
        "questions": [],
        "unresolved_items": [],
    }
