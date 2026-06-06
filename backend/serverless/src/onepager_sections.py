"""Onepaper section builders.

원페이퍼 화면에 보이는 각 영역을 만드는 순수 조립 함수들입니다.
세션 저장이나 Bedrock 호출은 하지 않고, 이미 저장된 responses를 화면용 JSON으로
정리하는 역할만 맡습니다.
"""

import re
from decimal import Decimal

from clinical_terms import find_symptom_quote, is_symptom_like_span, slot_to_name
from extraction_fallback import extract_agenda
from settings import ALLOW_RULE_FALLBACK
from utils import clean_quote, find_first_pattern, find_keyword_quote, unique, visit_label


def slot_to_symptom_slot(slot, qid, transcript=""):
    """IR matched_slot을 원페이퍼 증상 카드 schema로 바꿉니다."""
    slot_id = slot.get("slot_id") or slot.get("slot_ref")
    span_type = slot.get("span_type") or slot.get("type") or "symptom"
    if not is_symptom_like_span(span_type, slot_id):
        return None

    source_quote = clean_quote(slot.get("source_quote", ""))
    if not source_quote and transcript and slot_id:
        source_quote = find_symptom_quote(transcript, slot_id, [slot.get("name", "")]) or source_quote

    score = coerce_decimal(slot.get("score", Decimal("0.86")))
    if score <= 0 and not slot.get("ir_method"):
        score = Decimal("0.86")

    return {
        "slot_id": slot_id,
        "name": slot.get("name") or slot_to_name(slot_id),
        "source_question": qid,
        "source_quote": source_quote,
        "normalized_text": slot.get("normalized_text") or slot.get("name") or "",
        "status": slot.get("status") or "있음",
        "score": score,
        "alert": bool(slot.get("alert")),
        "explain": slot.get("explain") or "환자 발화에서 증상 표현을 확인했습니다.",
        "ir_method": slot.get("ir_method"),
        "ir_trace": slot.get("ir_trace") or {},
    }


def dedupe_symptom_slots(slots):
    """같은 표준 증상이 여러 문항에서 나오면 점수가 높은 카드만 남깁니다."""
    by_key = {}
    for slot in slots:
        key = slot.get("slot_id") or slot.get("name")
        if not key:
            continue
        old = by_key.get(key)
        if not old or Decimal(str(slot.get("score", 0))) >= Decimal(str(old.get("score", 0))):
            by_key[key] = slot
    return list(by_key.values())


def build_clinical_clues(q1, q2, q3, visit_type):
    """LLM이 만든 clinical_clues를 우선 사용하고, 허용 시에만 fallback 단서를 만듭니다."""
    structured_clues = []
    for qid, q in (("Q1", q1), ("Q2", q2), ("Q3", q3)):
        for item in ((q.get("structured") or {}).get("clinical_clues") or []):
            normalized = normalize_clinical_clue(item, qid)
            if normalized:
                structured_clues.append(normalized)
    if structured_clues:
        return unique_clues(structured_clues)
    if not ALLOW_RULE_FALLBACK:
        return []
    return build_fallback_clinical_clues(q1, q2, q3, visit_type)


def build_fallback_clinical_clues(q1, q2, q3, visit_type):
    """LLM clinical clue가 없을 때만 쓰는 최소 fallback 단서입니다."""
    clues = []
    idx = 1
    text1 = q1.get("text", "")
    text2 = q2.get("text", "")
    text3 = q3.get("text", "")
    related = [slot.get("name") for slot in q1.get("matched_slots", []) if slot.get("name")]

    onset_quote = find_first_pattern(text2, [
        r"한\s*그제\s*저녁부터",
        r"그제\s*저녁부터",
        r"그저께\s*저녁부터",
        r"그제부터",
        r"그저께부터",
        r"어제부터",
        r"어저께부터",
    ]) or find_first_pattern(text1, [r"어저께부터", r"어제부터", r"그제부터", r"그저께부터"])
    if onset_quote:
        source_q = "Q2" if onset_quote in text2 else "Q1"
        clues.append(clue(idx, "증상맥락", "시작시점", onset_quote, source_q, onset_quote, related))
        idx += 1

    if "괜찮" in text2 or "나아" in text2 or "호전" in text2:
        clues.append(clue(idx, "증상맥락", "현재양상", "오늘은 다소 호전/변동감 있음", "Q2", find_keyword_quote(text2, ["괜찮", "나아", "호전"]), related))
        idx += 1
    if "추" in text2 or "찬바람" in text2:
        clues.append(clue(idx, "증상맥락", "악화요인", "추위 노출 후 시작된 듯함", "Q2", find_keyword_quote(text2, ["추", "찬바람"]), []))
        idx += 1
    if "혈압" in text3:
        clues.append(clue(idx, "복약정보", "복용중", "혈압약 복용 중", "Q3", find_keyword_quote(text3, ["혈압"]), []))
        idx += 1

    supplements = []
    if "영양제" in text3:
        supplements.append("영양제")
    if "오메가" in text3:
        supplements.append("오메가3")
    if "종합비타민" in text3 or "비타민" in text3:
        supplements.append("종합비타민")
    if supplements:
        clues.append(clue(idx, "복약정보", "건강보조제", f"{', '.join(unique(supplements))} 복용 중", "Q3", find_keyword_quote(text3, ["영양제", "오메가", "종합비타민", "비타민"]), []))
        idx += 1

    if "먹는 약은 따로 없" in text3 or "약은 따로 없" in text3:
        clues.append(clue(idx, "복약정보", "처방약 없음", "평소 복용 처방약은 없다고 말함", "Q3", find_keyword_quote(text3, ["따로 없"]), []))
        idx += 1
    if "깜빡" in text3 or "못 먹" in text3:
        clues.append(clue(idx, "복약순응도", "누락", "복약 누락 가능성", "Q3", find_keyword_quote(text3, ["깜빡", "못 먹"]), []))
        idx += 1
    if visit_type == "followup" and "심" in q1.get("text", ""):
        clues.append(clue(idx, "재진경과", "악화", "증상 악화 호소", "Q1", find_keyword_quote(q1.get("text", ""), ["심"]), related))
    return clues


def clue(idx, category, label, summary, source_question, source_quote, related):
    """원페이퍼 clinical_clues 배열의 한 항목을 만듭니다."""
    return {
        "id": f"c{idx}",
        "category": category,
        "label": label,
        "summary": summary,
        "source_question": source_question,
        "source_quote": source_quote or summary,
        "priority": "일반",
        "related_symptoms": related,
        "action_hint": f"{label} 확인",
        "explain": "문진 원문에서 추출한 진료 맥락입니다.",
    }


def normalize_clinical_clue(item, fallback_qid):
    """LLM clinical clue 항목을 UI가 읽는 필드명으로 정리합니다."""
    if not isinstance(item, dict):
        return None
    summary = clean_quote(item.get("summary") or item.get("source_quote") or "")
    source_quote = clean_quote(item.get("source_quote") or summary)
    if not summary and not source_quote:
        return None
    label = clean_quote(item.get("label") or "문진단서")
    return {
        "id": item.get("id") or f"{fallback_qid}-{label}-{source_quote}",
        "category": clean_quote(item.get("category") or "증상맥락"),
        "label": label,
        "summary": summary or source_quote,
        "source_question": item.get("source_question") or fallback_qid,
        "source_quote": source_quote,
        "priority": item.get("priority") if item.get("priority") in ("일반", "우선") else "일반",
        "related_symptoms": item.get("related_symptoms") if isinstance(item.get("related_symptoms"), list) else [],
        "action_hint": item.get("action_hint") or f"{label} 확인",
        "explain": item.get("explain") or "Bedrock LLM이 문진 원문에서 추출한 진료 맥락입니다.",
    }


def unique_clues(clues):
    """동일한 clinical clue가 중복 표시되지 않게 정리합니다."""
    out = []
    seen = set()
    for item in clues:
        key = (item.get("category"), item.get("label"), item.get("summary"), item.get("source_quote"))
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["id"] = f"c{len(out) + 1}"
        out.append(item)
    return out


def normalize_agenda(q4):
    """Q4 patient questions를 원페이퍼 오른쪽 질문 카드 목록으로 변환합니다."""
    structured = q4.get("structured", {})
    questions = structured.get("questions") or q4.get("questions") or []
    text = q4.get("text", "")
    if not questions and not ALLOW_RULE_FALLBACK:
        return []
    if ALLOW_RULE_FALLBACK and text and (not questions or (len(questions) == 1 and questions[0].get("category") == "other")):
        questions = extract_agenda(text).get("questions", [])
    return [{
        "type": item.get("category", "other"),
        "category": item.get("category", "other"),
        "type_label": agenda_label(item.get("category")),
        "summary": item.get("summary", ""),
        "original_quote": item.get("original_quote", ""),
        "source_question": "Q4",
    } for item in questions]


def agenda_label(category):
    """agenda category enum을 의사용 표시명으로 바꿉니다."""
    return {
        "drug_drug_interaction": "복약 상호작용",
        "supplement_drug_interaction": "영양제 병용",
        "food_drug_interaction": "음식-약 상호작용",
        "treatment_duration": "복약 기간",
        "followup_visit": "재내원 기준",
    }.get(category, "환자 질문")


def build_review_items(slots, agenda, safety, clinical=None):
    """Nova Pro review가 실패했을 때만 쓰는 최소 fallback 체크리스트입니다."""
    items = []
    if safety:
        items.extend(["[우선] 객혈량과 시작 시점 확인", "[우선] 흉부 X-ray/객담 검사 고려"])
    names = {slot.get("name") for slot in slots}
    clinical_text = " ".join(
        clean_quote(c.get("summary") or c.get("source_quote") or c.get("label") or "")
        for c in (clinical or [])
    )
    if names & {"열", "발열"} or re.search(r"고열|발열|열", clinical_text):
        items.append("발열 여부와 실제 체온 확인")
    if "기침" in names or "가래" in names:
        items.append("가래 동반 여부와 색깔")
    if {"코막힘", "콧물", "재채기"} & names:
        items.append("비폐색/콧물 지속 정도와 알레르기 병력 확인")
    if any(c.get("label") == "건강보조제" for c in (clinical or [])):
        items.append("복용 중인 영양제 종류와 병용 가능성 확인")
    for item in agenda:
        category = item.get("category") or item.get("type")
        if category == "supplement_drug_interaction":
            items.append("처방약과 영양제 병용 가능 여부 안내")
        elif category == "followup_visit":
            items.append("증상 악화 시 중간 재내원 기준 안내")
        elif item.get("summary"):
            items.append(item["summary"] + " 답변")
    return unique(items) or ["문진 내용 직접 확인"]


def build_transfer_text(patient, slots, clinical, agenda, visit_type):
    """EMR 복사용 초안 문장을 원페이퍼 JSON 근거만으로 만듭니다."""
    symptoms = ", ".join(unique([slot.get("name") for slot in slots if slot.get("name")]))
    text = f"{patient.get('age') or '-'}세 {patient.get('gender') or ''} {visit_label(visit_type)} 환자."
    if symptoms:
        text += f" {symptoms} 호소."
    med = next((c.get("summary") for c in clinical if c.get("category") == "복약정보"), "")
    if med:
        text += f" {med}."
    if agenda:
        text += f" 환자 질문: {agenda[0].get('summary')}."
    return text


def coerce_decimal(value):
    """DynamoDB Decimal/float/string 값을 원페이퍼 점수 Decimal로 맞춥니다."""
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.86")
