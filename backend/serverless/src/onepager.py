"""Doctor onepaper assembly and session validation.

이 파일은 원페이퍼의 최상위 조립자입니다. 세부 섹션 생성은
`onepager_sections.py`, Nova Pro review는 `onepager_review.py`로 분리했습니다.
"""

from clinical_terms import find_safety_flag
from onepager_review import apply_bedrock_onepager_review
from onepager_sections import (
    build_clinical_clues,
    build_review_items,
    build_transfer_text,
    dedupe_symptom_slots,
    normalize_agenda,
    slot_to_symptom_slot,
)
from sessions import create_session, get_session, update_session
from settings import ENABLE_BEDROCK_REVIEW, USE_BEDROCK_LLM
from utils import format_hhmm, mask_name, normalize_visit_type, response


def validate_and_save(body):
    """문항 처리 결과를 세션에 저장하고 현재까지의 onepager를 다시 구성합니다."""
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    if not session_id or not question_id:
        return None, response(400, {"error": "missing_session_or_question"})

    session = get_session(session_id)
    if not session:
        session = create_session({"session_id": session_id, "visit_type": body.get("visit_type")})

    transcript = body.get("transcript") or ""
    structured = body.get("structured") or {}
    spans = body.get("spans") or []
    matched_slots = body.get("matched_slots") or []
    orchestration = body.get("orchestration") or {}
    pipeline_trace = body.get("pipeline_trace") or orchestration.get("trace") or []
    safety_flag = scan_safety(transcript, matched_slots)

    responses = session.get("responses", {})
    responses[question_id] = {
        "text": transcript,
        "spans": spans,
        "matched_slots": matched_slots,
        "structured": structured,
        "extract_method": body.get("method") or body.get("extract_method"),
        "llm_meta": body.get("llm_meta") or {},
        "orchestration": orchestration,
        "pipeline_trace": pipeline_trace,
        "confirmed": True,
    }
    question_results = session.get("question_results", {})
    question_results[question_id] = responses[question_id]

    risk = "high" if safety_flag or session.get("risk") == "high" else session.get("risk", "none")
    status = next_session_status(session, question_id, safety_flag)

    updated_base = {**session, "responses": responses, "question_results": question_results, "risk": risk}
    onepager = build_onepager(updated_base)
    update_session(session_id, {
        "responses": responses,
        "question_results": question_results,
        "risk": risk,
        "status": status,
        "onepager": onepager,
        "safety_flag": safety_flag or session.get("safety_flag"),
    })
    return {
        "validator_passed": True,
        "safety_flag": safety_flag,
        "errors": [],
        "onepager_ready": question_id == "Q4",
    }, None


def next_session_status(session, question_id, safety_flag):
    """문항 저장 이후 DynamoDB session status를 결정합니다."""
    if safety_flag or session.get("risk") == "high" or session.get("status") == "needs_priority":
        return "needs_priority"
    return "completed" if question_id == "Q4" else "in_progress"


def scan_safety(transcript, matched_slots):
    """객혈 등 우선 확인 표현을 deterministic rule로 감지합니다."""
    return find_safety_flag(transcript, matched_slots)


def build_onepager(session):
    """저장된 responses를 의사가 보는 단일 onepager JSON으로 조립합니다."""
    patient = session.get("patient", {})
    responses = session.get("responses", {})
    visit_type = normalize_visit_type(session.get("visit_type"))
    q1 = responses.get("Q1", {})
    q2 = responses.get("Q2", {})
    q3 = responses.get("Q3", {})
    q4 = responses.get("Q4", {})

    slots = collect_symptom_slots(q1, q3)
    clinical = build_clinical_clues(q1, q2, q3, visit_type)
    agenda = normalize_agenda(q4)
    safety = scan_safety(
        " ".join([r.get("text", "") for r in responses.values() if isinstance(r, dict)]),
        q1.get("matched_slots", []) + q3.get("matched_slots", []),
    )
    fallback_review_items = build_review_items(slots, agenda, safety, clinical)

    onepager = {
        "patient_summary": build_patient_summary(patient, session, visit_type),
        "agenda": agenda,
        "symptom_slots": slots,
        "clinical_clues": clinical,
        "doctor_brief": {"headline": "", "sections": []},
        "review_items": [],
        "transfer_text": build_transfer_text(patient, slots, clinical, agenda, visit_type),
        "safety_flags": [safety] if safety else [],
        "unresolved_items": [],
    }

    should_run_final_review = bool(q4) or bool(safety)
    if USE_BEDROCK_LLM and ENABLE_BEDROCK_REVIEW and responses and should_run_final_review:
        onepager = apply_bedrock_onepager_review(session, onepager, fallback_review_items)

    if not onepager.get("review_items"):
        onepager["review_items"] = fallback_review_items
        onepager["review_item_generation"] = {
            "method": "rule_fallback",
            "reason": (onepager.get("llm_review") or {}).get("error") or "llm_review_empty",
        }
    return onepager


def collect_symptom_slots(q1, q3):
    """Q1과 재진 Q3의 IR 결과를 원페이퍼 증상 카드로 모읍니다."""
    slots = []
    for slot in q1.get("matched_slots", []):
        normalized_slot = slot_to_symptom_slot(slot, "Q1", q1.get("text", ""))
        if normalized_slot:
            slots.append(normalized_slot)
    for slot in q3.get("matched_slots", []):
        normalized_slot = slot_to_symptom_slot(slot, "Q3", q3.get("text", ""))
        if normalized_slot:
            slots.append(normalized_slot)
    return dedupe_symptom_slots(slots)


def build_patient_summary(patient, session, visit_type):
    """상단 환자 요약 카드에 필요한 표시값을 만듭니다."""
    return {
        "display_name": patient.get("name") or mask_name(patient.get("full_name")),
        "age_text": f"{patient.get('age') or '-'}세",
        "sex": patient.get("gender") or "-",
        "department": patient.get("department") or "이비인후과",
        "received_at": format_hhmm(session.get("created_at")),
        "audio_duration_text": "확인됨",
        "visit_type": visit_type,
    }
