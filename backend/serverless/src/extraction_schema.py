"""Pydantic-backed validation for LLM extraction output.

이 파일은 extraction.py가 호출하는 얇은 adapter입니다. 실제 fixed schema는
`schemas/extraction.py`에 있고, 여기서는 question_id 같은 런타임 기본값만 보강한
뒤 Pydantic 검증 결과를 기존 파이프라인 형식으로 돌려줍니다.
"""

from copy import deepcopy

from schemas.extraction import validate_extraction_payload


def normalize_extraction_output(obj, transcript, question_id):
    """LLM 출력이 fixed schema와 quote grounding을 통과하는지 검증합니다.

    반환 형식은 기존 retry loop와 맞추기 위해 `(normalized, errors)`입니다.
    errors가 비어 있지 않으면 extraction.py가 repair prompt를 만들어 LLM에 다시
    요청합니다.
    """
    prepared = prepare_extraction_payload(obj, question_id)
    normalized, errors = validate_extraction_payload(prepared, transcript)
    if errors:
        return {"spans": [], "structured": empty_structured(transcript)}, errors
    return normalized, []


def prepare_extraction_payload(obj, question_id):
    """LLM 출력에 런타임 기본값을 채워 Pydantic 검증 대상으로 만듭니다.

    이 단계는 의미 값을 창작하지 않습니다. source_quote, category, slot_ref,
    spans/structured 같은 핵심 필드가 없으면 그대로 검증 실패하게 둡니다.
    단, clinical clue의 source_question은 현재 문항 ID라는 런타임 문맥이므로
    누락된 경우에만 보강합니다.
    """
    payload = deepcopy(obj) if isinstance(obj, dict) else {}
    structured = payload.get("structured")
    if isinstance(structured, dict) and isinstance(structured.get("clinical_clues"), list):
        for clue in structured["clinical_clues"]:
            if isinstance(clue, dict):
                clue.setdefault("source_question", question_id)
    return payload


def empty_structured(transcript):
    """검증 실패 시 DynamoDB에 잘못된 LLM 값을 저장하지 않기 위한 빈 구조입니다."""
    return {
        "standardized_text": transcript or "",
        "clinical_clues": [],
        "questions": [],
        "unresolved_items": [],
    }
