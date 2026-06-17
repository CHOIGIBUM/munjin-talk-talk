"""Bedrock extraction prompt templates.

문항별 LLM 추출에서 가장 자주 바뀔 수 있는 부분은 프롬프트입니다.
그래서 LLM 호출 노드에서 분리해, 프롬프트 엔지니어링을
할 때 이 파일만 집중해서 볼 수 있게 했습니다.
"""

from functools import lru_cache
from pathlib import Path

from domain_config import llm_symptom_slot_ids
from question_sets import prompt_question_text
from settings import LIGHT_MODEL_ID, STRONG_MODEL_ID
from utils import visit_label


FEWSHOT_EXAMPLES_PATH = Path(__file__).resolve().parent / "data" / "domain_packs" / "respiratory_fewshot.txt"


@lru_cache(maxsize=1)
def fewshot_examples() -> str:
    """호흡기 문진 few-shot 예시를 파일에서 읽어 prompt에 그대로 삽입합니다."""
    return FEWSHOT_EXAMPLES_PATH.read_text(encoding="utf-8")


def select_extraction_model(visit_type, question_id, question_type):
    """문항 난이도에 따라 Nova Pro/Lite를 선택합니다."""
    if question_type in ("chief_complaint", "progress", "new_symptoms") or question_id in ("Q1",):
        return STRONG_MODEL_ID
    return LIGHT_MODEL_ID


def build_extraction_prompt(
    visit_type,
    question_id,
    question_type,
    transcript,
    repair_note="",
    rag_context_note="",
    question_text_override="",
    question_set_id="",
):
    """Nova가 반드시 지켜야 할 quote grounding과 fixed schema를 명시합니다."""
    visit = visit_label(visit_type)
    server_text = prompt_question_text(visit_type, question_id, question_set_id or None)
    # 알려진 기본 문항은 서버 정의가 항상 우선입니다.
    # 클라이언트 override는 서버에 정의되지 않은 커스텀 문항 전용 fallback입니다.
    question_text = str(server_text or question_text_override or "").strip()
    allowed_slots = ", ".join(llm_symptom_slot_ids() + ["other"])
    return f"""
You are the semantic parsing LLM for a Korean clinic intake MVP.
Task: standardize dialect/colloquial speech, split meaning units, and tag the answer into the fixed schema.

Critical rules:
- Return JSON only. No markdown.
- Never diagnose. Do not infer facts that are not in the patient answer.
- Every source_quote and original_quote MUST be an exact continuous substring of the patient answer.
- If a fact is implied but no exact quote exists, omit it.
- Split multiple patient questions into separate items.
- Use concise Korean summaries for clinicians.
- source_quote is raw patient wording. normalized_text/summary is standardized Korean.
- Do NOT output score, confidence, probability, certainty, or risk percentage fields.
- If unsure, use status "확인필요" and explain the uncertainty in Korean instead of inventing a number.
- For medication, medication_denial, adherence_gap, and context spans, slot_ref MUST be "other".
- Only symptom/new/symptom_absent/progress spans may use symptom slot_ref values such as cough or fever.
- Classify symptom state by the patient's CURRENT meaning, not by keyword presence alone:
  * Current active symptom now present: type "symptom" or "new", status "있음".
  * New symptom after previous visit: type "new", status "있음".
  * Worse than before: type "progress_worsened", status "있음", and add clinical_clue label "악화" when grounded.
  * Still present/similar to before: type "progress_unchanged", status "있음".
  * Explicitly absent now, without saying it improved: type "symptom_absent", status "없음". Example: "열은 안 나요", "가래는 없어요".
  * Resolved or improved previous symptom that should NOT become a current complaint card: type "progress_improved", status "없음". Example: "열은 내렸다", "두통은 없어졌다", "다 나았다", "싹 내렸다".
- Active symptom types (symptom, new, progress_worsened, progress_unchanged) MUST NOT use status "없음".
- Non-active symptom types (symptom_absent, progress_improved) MUST use status "없음" and are not current complaint cards.
- For progress_improved, status "없음" means "not an active current complaint card"; it does NOT mean you may claim full disappearance unless the quote says it disappeared.
- If a symptom improved but is still currently present, split it:
  one active span for the remaining current symptom with status "있음", and one clinical_clue label "호전" for the improvement context.
- Do NOT convert caregiver fear or concern into dyspnea/chest_pain unless the patient or caregiver states actual breathing difficulty, chest pain, cyanosis, fainting, or inability to breathe.
- For Q4 patient_questions/unresolved_questions, a denial such as "없어요", "따로 없어요", "별로 없어요", or "궁금한 건 없어요" is NOT a patient question. Return questions: [].
- For symptom questions (chief_complaint, progress, new_symptoms), spans MUST contain at least one grounded meaning unit unless the patient clearly denies symptoms.
- clinical_clues are optional helper context. Include them only when category, label, and source_quote are all valid.
- clinical_clues.category MUST be exactly one of: 증상맥락, 복약정보, 복약순응도, 재진경과.
- clinical_clues.label MUST be exactly one of: 시작시점, 기간, 현재양상, 악화요인, 완화요인, 복용중, 처방약 없음, 건강보조제, 누락, 악화, 호전, 새 증상.
- clinical_clues.source_quote MUST NOT be empty. If no exact quote exists, omit that clinical_clue.
- The backend validates your output with a strict Pydantic schema. Missing required fields, invalid enum values, or extra fields will fail.

Visit type: {visit}
Question id: {question_id}
Question type: {question_type}
Question asked: {question_text}
Patient answer:
{transcript}

{rag_context_note}

{repair_note}

Allowed symptom slot_ref values when relevant:
{allowed_slots}

Allowed agenda categories:
drug_drug_interaction, supplement_drug_interaction, food_drug_interaction, treatment_duration, followup_visit, test_question, lifestyle, other

{fewshot_examples()}
Return exactly this JSON shape:
{{
  "spans": [
    {{
      "source_quote": "exact substring",
      "type": "symptom|new|symptom_absent|progress_improved|progress_worsened|progress_unchanged|medication|medication_denial|adherence_gap|context",
      "slot_ref": "allowed symptom slot_ref or other",
      "name": "display symptom name in Korean",
      "normalized_text": "standard Korean meaning",
      "status": "있음|없음|확인필요",
      "alert": false,
      "explain": "short Korean reason"
    }}
  ],
  "structured": {{
    "standardized_text": "standard Korean rewrite of the answer",
    "clinical_clues": [
      {{
        "category": "증상맥락|복약정보|복약순응도|재진경과",
        "label": "시작시점|기간|현재양상|악화요인|완화요인|복용중|처방약 없음|건강보조제|누락|악화|호전|새 증상",
        "summary": "clinician-facing concise Korean summary",
        "source_quote": "exact substring",
        "source_question": "{question_id}",
        "priority": "일반|우선",
        "related_symptoms": []
      }}
    ],
    "questions": [
      {{
        "category": "allowed agenda category",
        "summary": "concise patient question summary",
        "original_quote": "exact substring"
      }}
    ],
    "unresolved_items": []
  }}
}}
""".strip()


def build_extraction_repair_note(validation_errors, transcript):
    """검증 실패 이유를 LLM에게 다시 넘겨 같은 schema 안에서 재생성하게 합니다."""
    return f"""
Previous output failed validation and must be repaired.
Validation errors:
{validation_errors}

Repair instructions:
- Re-read the patient answer exactly as written.
- Every source_quote/original_quote must be copied as an exact continuous substring.
- Remove any item whose quote cannot be copied from the answer.
- If a clinical_clue has an invalid category/label or empty source_quote, either repair it to the exact allowed literal or remove that clinical_clue.
- For symptom questions, do not return spans: [] unless the answer clearly means no symptoms.
- Use symptom_absent/status "없음" for explicitly absent current symptoms, and progress_improved/status "없음" for resolved or improved previous symptoms.
- Do not use status "없음" with active symptom types such as symptom, new, progress_worsened, or progress_unchanged.
- Keep the same fixed JSON schema.
- Do not add facts, symptoms, medications, tests, or diagnoses that are absent.
- Do not output score, confidence, probability, certainty, or percentage fields.

Allowed clinical_clues.category literals:
증상맥락, 복약정보, 복약순응도, 재진경과

Allowed clinical_clues.label literals:
시작시점, 기간, 현재양상, 악화요인, 완화요인, 복용중, 처방약 없음, 건강보조제, 누락, 악화, 호전, 새 증상

Patient answer for exact quote checking:
{transcript}
""".strip()
