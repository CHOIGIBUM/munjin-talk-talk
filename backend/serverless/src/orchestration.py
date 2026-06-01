"""Question processing orchestration.

This module is the backend-side pipeline controller. The frontend sends one
confirmed transcript, then this graph runs the required stages in order:

1. Bedrock semantic extraction with schema/quote retry
2. Hybrid IR for symptom questions
3. Fixed-schema validation and DynamoDB save
4. Onepaper refresh, including final review when enough evidence exists

It is intentionally dependency-free for the Lambda MVP. The PIPELINE_GRAPH
constant mirrors the same node/edge shape that can later be moved into
LangGraph without changing the business modules.
"""

from clinical_terms import find_safety_flag
from extraction import extract_question
from onepager import validate_and_save
from retrieval import match_slots
from utils import normalize_visit_type, response

SYMPTOM_QUESTION_TYPES = {"chief_complaint", "progress", "new_symptoms"}

PIPELINE_GRAPH = {
    "nodes": [
        "input_transcript",
        "semantic_extraction",
        "schema_quote_validation",
        "hybrid_ir_match",
        "session_validation_save",
        "onepaper_refresh",
    ],
    "edges": [
        ("input_transcript", "semantic_extraction"),
        ("semantic_extraction", "schema_quote_validation"),
        ("schema_quote_validation", "hybrid_ir_match"),
        ("hybrid_ir_match", "session_validation_save"),
        ("session_validation_save", "onepaper_refresh"),
    ],
    "retry_policy": {
        "semantic_extraction": "EXTRACTION_RETRY_ATTEMPTS",
        "onepaper_final_review": "REVIEW_RETRY_ATTEMPTS",
    },
}


def process_answer(body):
    """Run the complete backend processing graph for one patient answer."""
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    question_type = body.get("question_type") or body.get("questionType")
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    transcript = (body.get("transcript") or "").strip()

    if not session_id or not question_id or not question_type:
        return None, response(400, {"error": "missing_required_fields"})
    if not transcript:
        return None, response(400, {"error": "empty_transcript"})

    preliminary_safety_flag = find_safety_flag(transcript, [])
    extracted = extract_question({
        **body,
        "session_id": session_id,
        "question_id": question_id,
        "question_type": question_type,
        "visit_type": visit_type,
        "transcript": transcript,
    })
    if extracted.get("validator_passed") is False or extracted.get("method") in {"bedrock_error", "bedrock_disabled"}:
        if preliminary_safety_flag:
            return save_safety_only_answer(
                body,
                session_id,
                question_id,
                question_type,
                visit_type,
                transcript,
                extracted,
                preliminary_safety_flag,
            )
        return None, response(422, {
            "error": "semantic_extraction_failed",
            "message": extracted.get("error") or "LLM schema/quote validation failed after retries.",
            "llm_meta": extracted.get("llm_meta") or {},
        })

    matched = {"matched_slots": [], "unmatched_spans": []}
    if question_type in SYMPTOM_QUESTION_TYPES:
        matched = match_slots({
            "session_id": session_id,
            "question_id": question_id,
            "visit_type": visit_type,
            "spans": extracted.get("spans", []),
        })

    validated, err = validate_and_save({
        "session_id": session_id,
        "question_id": question_id,
        "question_type": question_type,
        "visit_type": visit_type,
        "transcript": transcript,
        "spans": extracted.get("spans", []),
        "matched_slots": matched.get("matched_slots", []),
        "structured": extracted.get("structured", {}),
        "method": extracted.get("method"),
        "llm_meta": extracted.get("llm_meta") or {},
    })
    if err:
        return None, err

    return {
        "spans": extracted.get("spans", []),
        "structured": extracted.get("structured", {}),
        "matched_slots": matched.get("matched_slots", []),
        "unmatched_spans": matched.get("unmatched_spans", []),
        "validator_passed": bool(validated.get("validator_passed")),
        "safety_flag": validated.get("safety_flag"),
        "errors": validated.get("errors", []),
        "onepager_ready": validated.get("onepager_ready", False),
        "orchestration": {
            "graph": "serverless_pipeline_v1",
            "nodes": PIPELINE_GRAPH["nodes"],
            "question_type": question_type,
        },
    }, None


def save_safety_only_answer(body, session_id, question_id, question_type, visit_type, transcript, extracted, safety_flag):
    """Persist an urgent safety signal even when semantic extraction fails.

    Safety flags are deterministic guardrails, not a substitute for LLM
    semantic extraction. If the LLM schema/quote loop fails on a red-flag
    utterance, the intake must still be paused and visible to staff instead of
    disappearing behind a 422 response.
    """
    structured = {
        "standardized_text": transcript,
        "clinical_clues": [],
        "questions": [],
        "unresolved_items": [
            {
                "source_quote": safety_flag.get("matched_pattern") or transcript,
                "summary": "안전 플래그 감지 후 LLM 의미 추출 검증 실패",
            }
        ],
    }
    validated, err = validate_and_save({
        **body,
        "session_id": session_id,
        "question_id": question_id,
        "question_type": question_type,
        "visit_type": visit_type,
        "transcript": transcript,
        "spans": [],
        "matched_slots": [],
        "structured": structured,
        "method": extracted.get("method") or "safety_guardrail_only",
        "llm_meta": {
            **(extracted.get("llm_meta") or {}),
            "semantic_extraction_failed": True,
            "safety_saved_without_extraction": True,
        },
    })
    if err:
        return None, err
    return {
        "spans": [],
        "structured": structured,
        "matched_slots": [],
        "unmatched_spans": [],
        "validator_passed": True,
        "semantic_extraction_failed": True,
        "safety_flag": validated.get("safety_flag") or safety_flag,
        "errors": ["semantic_extraction_failed_but_safety_saved"],
        "onepager_ready": validated.get("onepager_ready", False),
        "orchestration": {
            "graph": "serverless_pipeline_v1",
            "nodes": PIPELINE_GRAPH["nodes"],
            "question_type": question_type,
            "safety_guardrail": "saved_before_llm_failure_response",
        },
    }, None
