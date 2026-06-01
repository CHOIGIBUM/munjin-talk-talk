"""Bedrock final review for doctor onepaper.

의료진 체크리스트와 EMR 초안은 단순 rule-base 목록으로 만들기 어렵습니다.
이 파일은 원페이퍼 JSON 전체를 Nova Pro에 넘겨 "의사라면 다음에 확인할 일"을
생성하고, 근거 없는 항목은 저장 전에 걸러냅니다.
"""

import hashlib
import json
import re

from llm import call_bedrock_json
from schemas.review import validate_review_payload
from settings import REVIEWER_MODEL_ID, REVIEW_MAX_TOKENS, REVIEW_RETRY_ATTEMPTS
from utils import clean_quote, json_default, normalize_text, unique, visit_label

UNSUPPORTED_TERM_PATTERNS = [
    r"항히스타민",
    r"비강\s*스프레이",
    r"스테로이드",
    r"항생제",
    r"항바이러스",
    r"X-ray|x-ray|엑스레이|흉부\s*방사선",
    r"\bCT\b|씨티",
    r"혈액\s*검사",
    r"결핵",
    r"폐렴",
    r"폐암|암",
]


def apply_bedrock_onepager_review(session, onepager, fallback_review_items=None):
    """Nova Pro review를 수행하고, 비어 있거나 근거 없는 결과면 제한 횟수만큼 재시도합니다."""
    last_error = ""
    attempts = max(1, REVIEW_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            prompt = build_onepager_review_prompt(session, onepager, fallback_review_items or [])
            if last_error:
                prompt += (
                    "\n\nPrevious final-review output failed validation: "
                    f"{last_error}. Regenerate grounded JSON only."
                )
            obj, raw_text = call_bedrock_json(prompt, REVIEWER_MODEL_ID, REVIEW_MAX_TOKENS)
        except Exception as exc:
            last_error = str(exc)
            continue

        # LLM이 만든 checklist JSON도 fixed schema를 통과해야만 다음 근거 검증으로 넘어갑니다.
        validated_obj, schema_errors = validate_review_payload(obj)
        if schema_errors:
            last_error = f"pydantic_schema_failed: {schema_errors}"
            continue

        reviewed = merge_review_output(onepager, validated_obj, raw_text, attempt)
        if reviewed.get("review_items") and reviewed.get("review_item_generation", {}).get("method") == "bedrock_nova_pro":
            return reviewed
        last_error = "review_items_empty_or_ungrounded"

    reviewed = dict(onepager)
    reviewed["llm_review"] = {
        "model_id": REVIEWER_MODEL_ID,
        "error": last_error or "review_failed",
        "attempts": attempts,
    }
    return reviewed


def merge_review_output(onepager, obj, raw_text, attempt):
    """Nova Pro 응답 중 검증을 통과한 필드만 onepager에 반영합니다."""
    reviewed = dict(onepager)
    if isinstance(obj.get("review_items"), list):
        items = [clean_quote(x) for x in obj.get("review_items", []) if clean_quote(x)]
        items = sanitize_review_items(items, onepager)
        if items:
            reviewed["review_items"] = unique(items)[:8]
            reviewed["review_item_generation"] = {
                "method": "bedrock_nova_pro",
                "model_id": REVIEWER_MODEL_ID,
                "attempts": attempt,
            }

    transfer = clean_quote(obj.get("transfer_text") or "")
    if transfer:
        reviewed["transfer_text"] = transfer
    if isinstance(obj.get("doctor_brief"), dict) and is_grounded_text(json.dumps(obj.get("doctor_brief"), ensure_ascii=False), onepager):
        reviewed["doctor_brief"] = obj.get("doctor_brief")

    reviewed["llm_review"] = {
        "model_id": REVIEWER_MODEL_ID,
        "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "issues": obj.get("issues") if isinstance(obj.get("issues"), list) else [],
        "attempts": attempt,
    }
    return reviewed


def build_onepager_review_prompt(session, onepager, heuristic_candidates=None):
    """의사가 볼 다음 행동 checklist를 만들도록 Nova Pro에 주는 프롬프트입니다."""
    payload = {
        "visit_type": visit_label(session.get("visit_type")),
        "patient": session.get("patient", {}),
        "responses": {
            qid: {
                "text": value.get("text", ""),
                "structured": value.get("structured", {}),
                "matched_slots": value.get("matched_slots", []),
            }
            for qid, value in (session.get("responses") or {}).items()
            if isinstance(value, dict)
        },
        "draft_onepager": onepager,
        "heuristic_candidates_do_not_copy_blindly": heuristic_candidates or [],
    }
    return f"""
You are a senior Korean outpatient physician preparing the next-step checklist before seeing this patient.
Your job is NOT to diagnose in place of the doctor and NOT to write treatment orders.
Your job is to read the full intake record like a clinician, identify what must be clarified or answered in the visit, and create practical physician tasks.

You will receive:
- patient metadata
- raw Q1-Q4 transcripts
- semantic parsing results from earlier LLM calls
- symptom_slots matched by BM25 + Titan embedding IR
- clinical_clues extracted from the conversation
- patient agenda/questions from Q4
- safety flags
- heuristic_candidates_do_not_copy_blindly: rough code-generated candidates that may be incomplete or wrong

Clinical tasking method:
Before writing JSON, silently run this checklist. Do not output the checklist or your reasoning.
A. What is the patient's main complaint and what details are still missing for a doctor to act?
B. What time course, progression, severity, trigger, or relieving factor needs clarification?
C. Are there medication, supplement, adherence, allergy, pregnancy, chronic disease, or interaction issues that change counseling?
D. What exact patient questions from Q4 must be answered by the doctor?
E. Are there red flags or safety issues that require priority handling?
F. Which tasks are actually supported by the transcript? Remove unsupported generic tasks.

Review item rules:
1. Generate review_items as the doctor's next actions, not as labels or summaries.
2. Each review_item must be grounded in at least one of: raw Q1-Q4 text, symptom_slots, clinical_clues, agenda, safety_flags, or matched_slots.ir_trace.
3. Use heuristic candidates only as weak hints. If they are not supported, ignore them.
4. Prefer concrete verbs: "확인", "질문", "안내", "상담", "검토", "평가". Avoid passive summaries.
5. Avoid vague items such as "원인 규명", "진단 필요", "상태 평가" by themselves. Specify what to check or answer.
6. Do NOT add fever/temperature tasks unless fever, heat, chill, high fever, antipyretic use, or body temperature appears in evidence.
7. Do NOT add X-ray, TB, pneumonia, cancer, antibiotics, or lab/test tasks unless safety_flags, patient wording, or clinician agenda explicitly supports them.
8. If Q4 contains patient questions, create one task per distinct question so the doctor can answer it.
   - The task must preserve the same medication/food/test names as the agenda.
   - Never introduce new drug classes, sprays, tests, or disease names that are absent from the evidence.
9. If medication/supplement/adherence appears, create a task only when it affects patient counseling, safety, interactions, or adherence.
10. Use "[우선]" only when safety_flags is non-empty or the raw patient wording clearly describes a red flag. Ordinary sore throat, nasal obstruction, cough, or runny nose must not be marked urgent.
11. Keep review_items short, Korean, and directly actionable. Good style: "콧물/코막힘 지속 정도와 알레르기 병력 확인".
12. Preserve uncertainty. Do not assert unsupported diagnoses or treatment decisions.
13. Return JSON only. No markdown, no prose outside JSON.
14. The backend validates this with a strict Pydantic schema. Missing required fields, invalid keys, or extra fields will fail.

Output quality target:
- Ordinary low-risk cases: 2 to 5 review_items.
- Safety or complex cases: up to 8 review_items, urgent items first.
- doctor_brief: 1 to 3 sections that summarize why those tasks matter.
- transfer_text: one concise Korean EMR-style sentence or two short sentences, grounded only in intake data.

Return schema:
{{
  "review_items": ["item"],
  "transfer_text": "EMR draft",
  "doctor_brief": {{
    "headline": "short summary",
    "sections": [
      {{"key": "symptoms|context|medication|agenda|safety", "title": "section title", "summary": "short summary", "items": []}}
    ]
  }},
  "issues": []
}}

Data:
{json.dumps(payload, ensure_ascii=False, default=json_default)}
""".strip()


def sanitize_review_items(items, onepager):
    """LLM이 근거 없는 검사/질환/우선 태그를 넣은 경우 저장 전에 걸러냅니다."""
    has_safety = bool(onepager.get("safety_flags"))
    sanitized = []
    for item in items:
        text = clean_quote(item)
        if not text:
            continue
        if not has_safety:
            text = re.sub(r"^\[우선\]\s*", "", text)
        if not is_grounded_text(text, onepager):
            continue
        sanitized.append(text)
    return sanitized


def evidence_text(onepager):
    """원페이퍼에 실제 존재하는 근거 텍스트만 모읍니다."""
    parts = []
    for slot in onepager.get("symptom_slots", []) or []:
        parts.extend([slot.get("name", ""), slot.get("source_quote", ""), slot.get("normalized_text", "")])
    for clue_item in onepager.get("clinical_clues", []) or []:
        parts.extend([clue_item.get("summary", ""), clue_item.get("source_quote", ""), clue_item.get("label", "")])
    for item in onepager.get("agenda", []) or []:
        parts.extend([item.get("summary", ""), item.get("original_quote", ""), item.get("type_label", "")])
    for flag in onepager.get("safety_flags", []) or []:
        parts.extend([flag.get("message", ""), flag.get("matched_pattern", ""), flag.get("label", "")])
    return normalize_text(" ".join(parts))


def is_grounded_text(text, onepager):
    """검사명/질환명처럼 위험한 확장 표현은 원페이퍼 근거가 있을 때만 허용합니다."""
    evidence = evidence_text(onepager)
    if not evidence:
        return True
    for pattern in UNSUPPORTED_TERM_PATTERNS:
        if re.search(pattern, text, flags=re.I) and not re.search(pattern, evidence, flags=re.I):
            return False
    return True
