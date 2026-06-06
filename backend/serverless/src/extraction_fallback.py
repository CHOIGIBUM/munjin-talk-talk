"""Deterministic fallback extraction helpers.

운영 설정에서는 `ALLOW_RULE_FALLBACK=false`이므로 이 파일은 기본적으로 쓰이지
않습니다. 단, 개발자가 fallback을 명시적으로 켰을 때만 최소한의 구조를 만들기
위해 분리해 둔 코드입니다.
"""

import re

from clinical_terms import SYMPTOM_RULES, find_symptom_quote
from utils import clean_quote, find_first_pattern, find_keyword_quote


def extract_rule_based(question_type, transcript):
    """LLM fallback이 허용된 경우에만 사용하는 문항별 경량 추출입니다."""
    spans = []
    structured = {}

    if question_type in ("chief_complaint", "progress", "new_symptoms"):
        for name, slot_id, keywords, alert in SYMPTOM_RULES:
            quote = find_symptom_quote(transcript, slot_id, keywords)
            if quote:
                spans.append({
                    "source_quote": quote,
                    "type": "symptom" if question_type == "chief_complaint" else "new",
                    "slot_ref": slot_id,
                    "name": name,
                    "alert": alert,
                })
    elif question_type == "onset":
        structured = extract_context(transcript)
        spans = structured.get("spans", [])
    elif question_type in ("current_medications", "adherence"):
        structured = extract_medication(transcript)
        spans = structured.get("spans", [])
    elif question_type in ("patient_questions", "unresolved_questions"):
        structured = extract_agenda(transcript)

    return {"spans": spans, "structured": structured, "transcript": transcript, "method": "rule_based_mvp"}


def extract_context(text):
    """시작 시점, 경과, 악화 요인 같은 맥락 단서를 아주 제한적으로 찾습니다."""
    spans = []
    onset_quote = find_first_pattern(text, [
        r"어저께부터",
        r"어제부터",
        r"그저께(?:\s*저녁)?부터",
        r"그제(?:\s*저녁)?부터",
        r"며칠\s*전부터",
        r"한\s*그제\s*저녁부터",
    ])
    if onset_quote:
        spans.append({"source_quote": onset_quote, "type": "onset"})
    if "괜찮" in text or "나아" in text or "호전" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["괜찮", "나아", "호전"]), "type": "course"})
    if "추" in text or "찬바람" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["추", "찬바람"]), "type": "context"})
    return {"spans": [s for s in spans if s.get("source_quote")], "estimated_onset_relative": "확인필요"}


def extract_medication(text):
    """복약 관련 fallback 추출입니다. 실제 운영에서는 Nova Lite 결과가 우선입니다."""
    spans = []
    meds = []
    if "혈압" in text:
        meds.append({"category": "antihypertensive", "patient_term": "혈압약"})
        spans.append({"source_quote": find_keyword_quote(text, ["혈압"]), "type": "medication"})
    if "영양제" in text:
        meds.append({"category": "supplement", "patient_term": "영양제"})
        spans.append({"source_quote": find_keyword_quote(text, ["영양제"]), "type": "medication"})
    if "오메가" in text or "오메가 쓰리" in text or "오메가3" in text:
        meds.append({"category": "supplement", "patient_term": "오메가3"})
        spans.append({"source_quote": find_keyword_quote(text, ["오메가"]), "type": "medication"})
    if "종합비타민" in text or "비타민" in text:
        meds.append({"category": "supplement", "patient_term": "종합비타민"})
        spans.append({"source_quote": find_keyword_quote(text, ["종합비타민", "비타민"]), "type": "medication"})
    if "먹는 약은 따로 없" in text or "약은 따로 없" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["따로 없"]), "type": "medication_denial"})
    if "깜빡" in text or "못 먹" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["깜빡", "못 먹"]), "type": "adherence_gap"})
    return {"spans": [s for s in spans if s.get("source_quote")], "extracted_medications": unique_medications(meds)}


def unique_medications(meds):
    """동일한 복약 항목이 여러 번 잡히지 않게 중복 제거합니다."""
    out = []
    seen = set()
    for med in meds:
        key = (med.get("category"), med.get("patient_term"))
        if key in seen:
            continue
        seen.add(key)
        out.append(med)
    return out


def extract_agenda(text):
    """환자 질문 문항 fallback용 질문 분리기입니다."""
    questions = []
    for sentence in split_question_sentences(text):
        if not sentence:
            continue
        if ("감기약" in sentence or "혈압약" in sentence) and "같이" in sentence:
            questions.append({
                "category": "drug_drug_interaction",
                "summary": "혈압약-감기약 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif ("처방" in sentence or "약" in sentence) and ("영양제" in sentence or "오메가" in sentence or "비타민" in sentence) and ("같이" in sentence or "먹어" in sentence):
            questions.append({
                "category": "supplement_drug_interaction",
                "summary": "처방약-영양제 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif "양파" in sentence:
            questions.append({
                "category": "food_drug_interaction",
                "summary": "양파즙 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif "언제까지" in sentence or "며칠" in sentence:
            questions.append({
                "category": "treatment_duration",
                "summary": "복약 기간 문의",
                "original_quote": sentence,
            })
        elif ("다시" in sentence or "와도" in sentence or "내원" in sentence or "방문" in sentence) and ("심해" in sentence or "증상" in sentence or "중간" in sentence):
            questions.append({
                "category": "followup_visit",
                "summary": "증상 악화 시 중간 재내원 가능 여부 문의",
                "original_quote": sentence,
            })
    if not questions and text:
        questions.append({"category": "other", "summary": clean_quote(text)[:40], "original_quote": clean_quote(text)})
    return {"questions": questions, "uncategorized_remnant": ""}


def split_question_sentences(text):
    """한 발화 안에 여러 환자 질문이 섞인 경우 문장 단위로 나눕니다."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    normalized = re.sub(r"\s+또\s+(?=뭐|혹시|증상|약|언제|와도)", ". 또 ", normalized, count=1)
    parts = [clean_quote(part) for part in re.split(r"[.?!。]+", normalized)]
    return [part for part in parts if part]
