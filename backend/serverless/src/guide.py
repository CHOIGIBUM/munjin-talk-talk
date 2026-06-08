"""Patient guide generation after physician review.

의사가 원페이퍼에서 환자 질문에 답하면 Nova Lite가 어르신이 읽기 쉬운 안내문으로
재작성합니다. 의사가 직접 남긴 강조사항은 LLM이 바꾸지 않고 별도 카드에 그대로
표시합니다. LLM 안내문이 schema/품질 검증을 통과하지 못하면 rule-base 문장을 대신
만들지 않고 validator 실패로 드러냅니다.
"""

import hashlib
import json

from llm import call_bedrock_json
from schemas.guide import validate_guide_payload
from sessions import get_session, update_session
from settings import GUIDE_MAX_TOKENS, GUIDE_MODEL_ID
from utils import clean_quote, compact_ir, json_default, normalize_text, now_iso, response


def save_doctor_response(body):
    """`POST /doctor-response` 진입점. 의사 답변 저장 후 안내문 생성을 시도합니다."""
    session_id = body.get("session_id") or body.get("sessionId")
    session = get_session(session_id)
    if not session:
        return None, response(404, {"error": "session_not_found"})

    answers = body.get("answers") or []
    patient_instruction = (
        body.get("patient_instruction")
        or body.get("patientInstruction")
        or body.get("additional_notes")
        or body.get("additionalNotes")
        or ""
    )
    guide = generate_patient_guide(session, answers, patient_instruction)
    validator_passed = not answers or bool(guide.get("items"))

    doctor_review = {
        "answers": answers,
        "patient_instruction": patient_instruction,
        "additional_notes": patient_instruction,
        "reviewed_at": now_iso(),
    }
    update_session(session_id, {
        "doctor_review": doctor_review,
        "patient_guide": guide,
        "status": "reviewed",
    })
    return {
        "doctor_review_saved": True,
        "patient_guide_generated": bool(guide.get("items")),
        "validator_passed": validator_passed,
        "patient_guide": guide,
    }, None


def generate_patient_guide(session, answers, patient_instruction):
    """Nova Lite 안내문을 만들고, 실패하면 빈 안내문과 실패 이유만 저장합니다."""
    if not answers:
        return {
            "generated_at": now_iso(),
            "items": [],
            "delivery_options": ["screen", "tts", "print"],
            "generation_method": "no_patient_question_answers",
        }
    try:
        guide = generate_patient_guide_bedrock(session, answers, patient_instruction)
        if is_patient_guide_usable(guide, answers):
            guide["generation_method"] = "bedrock_nova_lite_grounded"
            return guide
        guide_error = "bedrock_output_failed_quality_validation"
    except Exception as exc:
        guide_error = str(exc)

    return {
        "generated_at": now_iso(),
        "items": [],
        "delivery_options": ["screen", "tts", "print"],
        "generation_method": "bedrock_nova_lite_failed",
        "guide_warning": guide_error,
    }


def generate_patient_guide_bedrock(session, answers, patient_instruction):
    """의사 답변을 쉬운 한국어 bullet 안내문으로 바꾸는 Bedrock 호출입니다."""
    payload = {
        "patient": session.get("patient", {}),
        "onepager": session.get("onepager", {}),
        "doctor_answers": answers,
        "doctor_patient_instruction_displayed_separately": patient_instruction,
    }
    prompt = f"""
You are a Korean patient instruction writer for older adults after a clinic visit.
Convert doctor's answers into easy Korean guide items.

Rules:
- Do not add medical facts not present in doctor_answers or notes.
- Do not copy the doctor's answer verbatim. Rewrite it into polite, easy Korean for an older patient.
- Preserve the doctor's meaning, permission, warnings, timing, and follow-up conditions.
- Keep each bullet short and clear. Prefer 1-3 sentences per question.
- Avoid difficult medical terms unless the doctor used them.
- Do not output generic placeholders like "진료실에서 안내받은 내용을 따라 주세요."
- The field doctor_patient_instruction_displayed_separately is shown as a separate blue "선생님 강조사항" card. Do not duplicate it inside question answer items.
- Return JSON only.
- The backend validates this with a strict Pydantic schema. Missing required fields or extra fields will fail.

Few-shot examples:
Input doctor answer: "혈압약은 계속 복용해도 되고, 감기약은 처방받은 약만 복용하도록 설명."
Output answer_simple: ["혈압약은 평소처럼 계속 드세요.", "감기약은 오늘 처방받은 약만 드시는 것이 안전합니다."]

Input doctor answer: "영양제는 이번 처방약과 큰 상호작용은 없으나 새 약 추가 시 재확인."
Output answer_simple: ["현재 영양제는 이번 약과 같이 드셔도 됩니다.", "나중에 다른 약이 추가되면 병원이나 약국에 다시 확인해 주세요."]

Schema:
{{
  "items": [
    {{
      "question": "patient question summary",
      "answer_simple": ["short instruction sentence"],
      "tts_emphasis_words": ["important word"]
    }}
  ],
  "delivery_options": ["screen", "tts", "print"]
}}

Data:
{json.dumps(payload, ensure_ascii=False, default=json_default)}
""".strip()
    obj, raw_text = call_bedrock_json(prompt, GUIDE_MODEL_ID, GUIDE_MAX_TOKENS)
    validated_obj, schema_errors = validate_guide_payload(obj)
    if schema_errors:
        raise ValueError(f"guide_pydantic_schema_failed: {schema_errors}")

    items = []
    for item in validated_obj.get("items", []):
        answer_simple = [clean_quote(x) for x in item.get("answer_simple", []) if clean_quote(x)]
        if not answer_simple:
            continue
        items.append({
            "question": clean_quote(item.get("question") or "진료 안내"),
            "answer_simple": answer_simple,
            "tts_emphasis_words": [clean_quote(x) for x in item.get("tts_emphasis_words", []) if clean_quote(x)],
        })
    return {
        "generated_at": now_iso(),
        "items": items,
        "delivery_options": validated_obj.get("delivery_options") or ["screen", "tts", "print"],
        "llm_meta": {
            "model_id": GUIDE_MODEL_ID,
            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        },
    }


def is_patient_guide_usable(guide, answers):
    """빈 안내문, 너무 일반적인 문장, 의사 답변 원문 복사를 거부합니다."""
    items = guide.get("items") if isinstance(guide, dict) else []
    if not isinstance(items, list) or not items:
        return False
    generic_patterns = [
        "진료실에서 안내받은 내용을 따라 주세요",
        "오늘 진료에서 안내받은 내용을 확인해 주세요",
        "의사 선생님의 안내를 따라 주세요",
    ]
    source_answers = [normalize_text(ans.get("answer_text") or ans.get("answer") or "") for ans in (answers or [])]
    usable_count = 0
    for idx, item in enumerate(items):
        answer_simple = item.get("answer_simple") if isinstance(item, dict) else []
        if not isinstance(answer_simple, list):
            continue
        cleaned = [clean_quote(x) for x in answer_simple if clean_quote(x)]
        if not cleaned:
            continue
        joined = " ".join(cleaned)
        if any(pattern in joined for pattern in generic_patterns):
            continue
        source = source_answers[idx] if idx < len(source_answers) else " ".join(source_answers)
        if source and compact_ir(joined) == compact_ir(source):
            continue
        usable_count += 1
    return usable_count > 0


def get_guide(session_id):
    """안내문 화면에서 사용할 patient_guide와 doctor note를 함께 반환합니다."""
    session = get_session(session_id)
    if not session:
        return None
    guide = session.get("patient_guide") or {
        "generated_at": now_iso(),
        "items": [],
        "delivery_options": ["screen", "tts", "print"],
        "generation_method": "not_generated",
    }
    return {
        "session_id": session_id,
        "patient_name_masked": (session.get("patient") or {}).get("name", "환자"),
        "patient_guide": guide,
        "doctor_additional_notes": (
            (session.get("doctor_review") or {}).get("patient_instruction")
            or (session.get("doctor_review") or {}).get("additional_notes", "")
        ),
    }
