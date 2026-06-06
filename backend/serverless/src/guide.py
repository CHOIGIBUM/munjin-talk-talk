"""Patient guide generation after physician review.

의사가 원페이퍼에서 환자 질문에 답하면, 그 답변을 어르신이 읽기 쉬운 안내문으로
재작성합니다. 단, 의사가 직접 남긴 강조사항은 LLM이 바꾸지 않고 원문 그대로
별도 카드에 표시합니다.
"""

import hashlib
import json
import re

from llm import call_bedrock_json
from schemas.guide import validate_guide_payload
from sessions import get_session, update_session
from settings import ENABLE_BEDROCK_GUIDE, GUIDE_MAX_TOKENS, GUIDE_MODEL_ID, USE_BEDROCK_LLM
from utils import clean_quote, compact_ir, json_default, normalize_text, now_iso, response, unique

def save_doctor_response(body):
    """`POST /doctor-response` 진입점. 의사 답변 저장 후 안내문을 생성합니다."""
    session_id = body.get("session_id") or body.get("sessionId")
    session = get_session(session_id)
    if not session:
        return None, response(404, {"error": "session_not_found"})
    answers = body.get("answers") or []
    patient_instruction = body.get("patient_instruction") or body.get("patientInstruction") or body.get("additional_notes") or body.get("additionalNotes") or ""
    guide = generate_patient_guide(session, answers, patient_instruction)
    if not guide["items"]:
        guide["items"] = default_guide_items(session)
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
    return {"doctor_review_saved": True, "patient_guide_generated": True, "validator_passed": True, "patient_guide": guide}, None


def generate_patient_guide(session, answers, patient_instruction):
    """Nova Lite 안내문을 우선 쓰고, 품질 검증 실패 시 deterministic fallback을 씁니다."""
    if USE_BEDROCK_LLM and ENABLE_BEDROCK_GUIDE:
        try:
            guide = generate_patient_guide_bedrock(session, answers, patient_instruction)
            if is_patient_guide_usable(guide, answers):
                guide["generation_method"] = "bedrock_nova_lite_grounded"
                return guide
        except Exception as exc:
            guide_error = str(exc)
        else:
            guide_error = "bedrock_output_failed_validation"
    else:
        guide_error = "bedrock_guide_disabled"

    return {
        "generated_at": now_iso(),
        "items": doctor_answer_guide_items(answers, patient_friendly=True),
        "delivery_options": ["screen", "tts", "print"],
        "generation_method": "deterministic_patient_friendly_fallback",
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
    # 환자에게 직접 보이는 안내문이므로 LLM JSON 형식을 먼저 엄격히 검증합니다.
    validated_obj, schema_errors = validate_guide_payload(obj)
    if schema_errors:
        raise ValueError(f"guide_pydantic_schema_failed: {schema_errors}")

    items = []
    for item in validated_obj.get("items", []):
        answers_simple = [clean_quote(x) for x in item.get("answer_simple", []) if clean_quote(x)]
        if not answers_simple:
            continue
        items.append({
            "question": clean_quote(item.get("question") or "진료 안내"),
            "answer_simple": answers_simple,
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


def split_answer(text):
    parts = [p.strip() for p in re.split(r"[.\n]", text or "") if p.strip()]
    return parts or ["진료실에서 안내받은 내용을 따라 주세요."]


def doctor_answer_guide_items(answers, patient_friendly=False):
    items = []
    for ans in answers or []:
        answer_text = ans.get("answer_text") or ans.get("answer") or ""
        if patient_friendly:
            answer_simple = rewrite_answer_for_patient(answer_text)
        else:
            answer_simple = split_answer(answer_text)
        items.append({
            "question": ans.get("question_summary") or ans.get("question") or "환자 질문",
            "answer_simple": answer_simple,
            "tts_emphasis_words": extract_emphasis_words(answer_text),
        })
    return items


def rewrite_answer_for_patient(text):
    if not normalize_text(text):
        return ["진료실에서 안내받은 내용을 확인해 주세요."]
    sentences = split_answer(text)
    out = []
    for sentence in sentences:
        s = normalize_text(sentence)
        s = s.replace("추후", "나중에")
        s = s.replace("검토 필요", "다시 확인이 필요합니다")
        s = s.replace("검토", "확인")
        if "복용 가능" in s or "먹어도" in s or "드셔도" in s:
            if "문제 없이" in s:
                s = "같이 드셔도 괜찮습니다"
            else:
                s = s.replace("복용 가능", "드셔도 됩니다")
        if "약물 추가" in s or "다른 약" in s:
            s = "나중에 다른 약이 추가되면 병원이나 약국에 다시 확인해 주세요"
        if not re.search(r"(요|다|세요|습니다)$", s):
            s += "습니다"
        out.append(s)
    return unique(out) or ["진료실에서 안내받은 내용을 확인해 주세요."]


def is_patient_guide_usable(guide, answers):
    """너무 일반적인 문장, 빈 안내문, 의사 답변 원문 복사를 거부합니다."""
    items = guide.get("items") if isinstance(guide, dict) else []
    if not isinstance(items, list) or not items:
        return False
    generic_patterns = [
        "진료실에서 안내받은 내용을 따라 주세요",
        "오늘 진료에서 안내받은 내용을 확인해 주세요",
        "의사 선생님의 안내를 따라 주세요",
    ]
    answer_texts = [normalize_text(ans.get("answer_text") or ans.get("answer") or "") for ans in (answers or [])]
    usable_count = 0
    for idx, item in enumerate(items):
        answers_simple = item.get("answer_simple") if isinstance(item, dict) else []
        if not isinstance(answers_simple, list):
            continue
        cleaned = [clean_quote(x) for x in answers_simple if clean_quote(x)]
        if not cleaned:
            continue
        joined = " ".join(cleaned)
        if any(pattern in joined for pattern in generic_patterns):
            continue
        source = answer_texts[idx] if idx < len(answer_texts) else " ".join(answer_texts)
        if source and compact_ir(joined) == compact_ir(" ".join(split_answer(source))):
            continue
        usable_count += 1
    return usable_count > 0


def extract_emphasis_words(text):
    words = []
    for token in ("복용", "약", "영양제", "검토", "중단", "재내원", "검사", "X-ray"):
        if token in str(text or ""):
            words.append(token)
    return unique(words)[:5]


def default_guide_items(session):
    agenda = (session.get("onepager") or {}).get("agenda") or []
    if not agenda:
        return [{"question": "진료 안내", "answer_simple": ["오늘 진료에서 안내받은 내용을 확인해 주세요."], "tts_emphasis_words": []}]
    return [{"question": item.get("summary", "환자 질문"), "answer_simple": ["진료실에서 안내받은 내용을 따라 주세요."], "tts_emphasis_words": []} for item in agenda]


def get_guide(session_id):
    """안내문 화면에서 사용할 patient_guide와 doctor note를 함께 반환합니다."""
    session = get_session(session_id)
    if not session:
        return None
    guide = session.get("patient_guide")
    if not guide:
        guide = {"generated_at": now_iso(), "items": default_guide_items(session), "delivery_options": ["screen", "tts", "print"]}
    return {
        "session_id": session_id,
        "patient_name_masked": (session.get("patient") or {}).get("name", "환자"),
        "patient_guide": guide,
        "doctor_additional_notes": (session.get("doctor_review") or {}).get("patient_instruction") or (session.get("doctor_review") or {}).get("additional_notes", ""),
    }
