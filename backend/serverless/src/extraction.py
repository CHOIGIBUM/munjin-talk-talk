"""Question-level semantic parsing entrypoint.

이 파일은 `/extract` 또는 `/process-answer`에서 호출되는 얇은 진입점입니다.
실제 프롬프트와 schema/source_quote 검증은 전용 파일로 분리했습니다.
"""

import hashlib

from extraction_prompts import (
    build_extraction_prompt,
    build_extraction_repair_note,
    select_extraction_model,
)
from extraction_schema import normalize_extraction_output
from llm import call_bedrock_json
from settings import (
    EXTRACTION_RETRY_ATTEMPTS,
    MAX_LLM_TOKENS,
)
from utils import normalize_visit_type


def extract_question(body):
    """Bedrock LLM extraction을 수행하고 실패를 rule-base로 숨기지 않습니다."""
    transcript = (body.get("transcript") or "").strip()
    try:
        return extract_question_bedrock(body)
    except Exception as exc:
        return extraction_error(transcript, "bedrock_error", str(exc))


def extract_question_bedrock(body):
    """LLM 추출을 수행하고 schema/source_quote 검증 실패 시 bounded retry를 돌립니다."""
    question_type = body.get("question_type") or body.get("questionType")
    question_id = body.get("question_id") or body.get("questionId") or ""
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    transcript = (body.get("transcript") or "").strip()
    if not transcript:
        return {"spans": [], "structured": {}, "transcript": "", "method": "bedrock_nova"}

    model_id = select_extraction_model(visit_type, question_id, question_type)
    repair_note = ""
    last_normalized = None
    last_raw_text = ""
    last_errors = []
    attempts = max(1, EXTRACTION_RETRY_ATTEMPTS)

    for attempt in range(1, attempts + 1):
        prompt = build_extraction_prompt(visit_type, question_id, question_type, transcript, repair_note)
        obj, raw_text = call_bedrock_json(prompt, model_id, MAX_LLM_TOKENS)
        normalized, validation_errors = normalize_extraction_output(obj, transcript, question_id, question_type)
        last_normalized = normalized
        last_raw_text = raw_text
        last_errors = validation_errors
        if not validation_errors:
            break
        repair_note = build_extraction_repair_note(validation_errors, transcript)

    last_normalized = last_normalized or {"spans": [], "structured": {}}
    last_normalized.update({
        "transcript": transcript,
        "method": "bedrock_nova",
        "validator_passed": not last_errors,
        "llm_meta": {
            "model_id": model_id,
            "raw_sha256": hashlib.sha256(last_raw_text.encode("utf-8")).hexdigest(),
            "validation_errors": last_errors,
            "attempts": attempt,
            "retry_loop": "schema_quote_repair",
        },
    })
    return last_normalized


def extraction_error(transcript, method, message):
    """LLM 필수 모드에서 실패했을 때 rule-base로 숨기지 않고 명시적으로 반환합니다."""
    return {
        "spans": [],
        "structured": {},
        "transcript": transcript,
        "method": method,
        "validator_passed": False,
        "error": message,
    }
