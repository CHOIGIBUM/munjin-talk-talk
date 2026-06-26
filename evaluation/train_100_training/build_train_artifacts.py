"""Build runtime artifacts from the clean train_100 dataset.

This script is intentionally deterministic. The patient utterances are already
LLM-rendered in ``evaluation/generated/train_100/cases.jsonl``; this script only
turns accepted training rows into runtime JSON files and records provenance.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TRAIN_CASES_PATH = ROOT / "evaluation" / "generated" / "train_100" / "cases.jsonl"
SYMPTOM_INDEX_PATH = ROOT / "backend" / "serverless" / "src" / "data" / "symptom_index.json"
DOMAIN_PACK_PATH = ROOT / "backend" / "serverless" / "src" / "data" / "domain_packs" / "respiratory.json"
FEWSHOT_DIR = ROOT / "backend" / "serverless" / "src" / "data" / "fewshots" / "respiratory"
REPORT_PATH = ROOT / "evaluation" / "train_100_training" / "training_report.json"


SLOT_BY_SYMPTOM = {
    "감기 증상": "common_cold_symptoms",
    "객혈": "hemoptysis",
    "검은색 가래": "black_sputum",
    "거품이 섞인 가래": "foamy_sputum",
    "가래": "sputum",
    "가슴 답답": "chest_discomfort",
    "가슴 두근거림": "palpitation",
    "구토": "vomiting",
    "권태감": "malaise",
    "근력 약화": "muscle_weakness",
    "근육통": "myalgia",
    "기운없음": "low_energy",
    "기침": "cough",
    "눈꼽": "eye_discharge",
    "눈의 충혈": "eye_redness",
    "말초부종": "peripheral_edema",
    "목소리 변화": "voice_change",
    "목의 통증": "sore_throat",
    "발한": "sweating",
    "복부 통증": "abdominal_pain",
    "복부팽만감": "abdominal_bloating",
    "부정맥": "arrhythmia",
    "불안": "anxiety",
    "빈맥": "tachycardia",
    "사래걸림": "choking",
    "사지 부종": "limb_edema",
    "삼키기 곤란": "dysphagia",
    "설사": "diarrhea",
    "식욕부진": "appetite_loss",
    "어지러움": "dizziness",
    "열": "fever",
    "오한": "chills",
    "온몸이 떨림": "whole_body_tremor",
    "운동 시 호흡곤란": "exertional_dyspnea",
    "재채기": "sneezing",
    "천명음": "wheezing",
    "창백": "pallor",
    "콧물": "rhinorrhea",
    "코막힘": "nasal_obstruction",
    "피로감": "fatigue",
    "하지부종": "leg_edema",
    "호흡곤란": "dyspnea",
    "화농성 객담": "purulent_sputum",
    "흉통": "chest_pain",
}


KEYWORDS_BY_SYMPTOM = {
    "감기 증상": ["감기", "감기 기운", "으슬", "찌뿌둥", "개운하지", "개운치"],
    "객혈": ["피 섞", "피가 섞", "피가래", "피가 비쳐", "피가 보여", "피가", "피는", "객혈"],
    "검은색 가래": ["까맣", "거뭇", "검은", "검은색 가래"],
    "거품이 섞인 가래": ["거품", "거품 낀", "거품이 섞인"],
    "가래": ["가래", "목에 붙", "뱉게", "끼어"],
    "가슴 답답": ["가슴 답답", "가심이 답답", "꽉 막힌", "답답한 건 아직"],
    "가슴 두근거림": ["두근", "심장이 뛰", "심장이 빨리 뛰"],
    "구토": ["토했", "토하", "울렁"],
    "권태감": ["축 처지", "하기 싫", "찌뿌둥"],
    "근력 약화": ["힘이 잘 안 들어", "팔다리에 힘", "근력"],
    "근육통": ["몸살", "쑤시", "온몸이 쑤시"],
    "기운없음": ["힘이 없", "축 처져", "기운"],
    "기침": ["기침", "기침이", "기침은", "기침을", "기침하고", "기침할", "콜록"],
    "눈꼽": ["눈꼽", "눈곱", "눈 뜨기 불편"],
    "눈의 충혈": ["눈이 빨갛", "충혈", "벌겋"],
    "말초부종": ["손끝", "발끝", "반지가 꽉", "말초부종"],
    "목소리 변화": ["목소리", "쉬어서", "잠겨", "잘 안 나와"],
    "목의 통증": ["목이 칼칼", "목이 따갑", "목이 아프", "목이 아픈", "목 아퍼", "아푸", "인후통"],
    "발한": ["식은땀", "땀이", "발한"],
    "복부 통증": ["배가 아프", "배가 아픈", "배 아퍼", "배가 살살 아프", "복부 통증"],
    "복부팽만감": ["배가 빵빵", "더부룩", "복부팽만"],
    "부정맥": ["맥이 고르지", "건너뛰", "들쑥날쑥", "툭 빠지는"],
    "불안": ["불안", "마음이 불안", "마음이 걱정"],
    "빈맥": ["너무 빨리 뛰", "심장이 빨리", "빈맥"],
    "사래걸림": ["사레", "사래", "사레가", "사래가", "사레 들", "사래 들"],
    "사지 부종": ["손발이", "전보다 부어서", "사지 부종"],
    "삼키기 곤란": ["삼키", "잘 안 넘어", "목에 걸린"],
    "설사": ["설사", "화장실을 자꾸"],
    "식욕부진": ["입맛", "식욕"],
    "어지러움": ["어지", "핑 돌"],
    "열": ["열", "열이", "열은", "열나", "열이 나", "열은 나", "뜨겁", "다시 올라"],
    "오한": ["으슬으슬", "추워", "춥", "몸이 떨"],
    "온몸이 떨림": ["덜덜 떨", "온몸이 떨"],
    "운동 시 호흡곤란": ["계단", "걸어도 숨", "움직여도 숨", "운동 시"],
    "재채기": ["재채기"],
    "천명음": ["쌕쌕", "쌕쌕 소리", "천명"],
    "창백": ["핏기가", "창백", "싹 빠진"],
    "콧물": ["콧물", "코물", "훌쩍"],
    "코막힘": ["코가 막", "코가 꽉 막", "코가 맥혀", "맥혀"],
    "피로감": ["피곤", "누워 있고", "더 피곤"],
    "하지부종": ["다리가 붓", "다리가 퉁퉁", "신발이 꽉"],
    "호흡곤란": ["숨이 차", "숨이 벅차", "숨쉬기 갑갑", "말하기가 힘든"],
    "화농성 객담": ["누런 가래", "진한 가래", "누렇고 진"],
    "흉통": ["가슴 한쪽", "가심 한쪽", "가슴이 아픈", "가심이 아픈", "콕콕 아프", "찌르듯 아픈", "결리듯 아파"],
}


ALIAS_PATTERNS = {
    "감기 증상": r"감기\s*기운|감기\s*걸린|몸이\s*(?:으슬|찌뿌둥|개운)",
    "객혈": r"피(?:가|는)?\s*(?:조금\s*)?(?:섞여|비쳐|보여|나왔|안\s*보)|피\s*섞|피가래|객혈",
    "검은색 가래": r"가래.{0,8}(?:까맣|거뭇|검은)|(?:까맣|거뭇|검은).{0,8}가래",
    "거품이 섞인 가래": r"가래.{0,8}거품|거품.{0,8}가래",
    "가래": r"가래|목에\s*가래|목에\s*붙은|뱉게\s*돼",
    "가슴 답답": r"가[슴심].{0,6}(?:답답|꽉\s*막)",
    "가슴 두근거림": r"가슴.{0,6}두근|심장.{0,10}뛰",
    "구토": r"토했|토하|울렁",
    "권태감": r"축\s*처지|아무것도\s*하기\s*싫|찌뿌둥",
    "근력 약화": r"팔다리.{0,8}힘|힘이\s*잘\s*안\s*들어",
    "근육통": r"몸살|온몸.{0,6}쑤시|근육통",
    "기운없음": r"힘이\s*(?:하나도\s*)?없|기운\s*없|축\s*처져",
    "기침": r"기침|콜록",
    "눈꼽": r"눈[꼽곱]|눈\s*뜨기\s*불편",
    "눈의 충혈": r"눈.{0,6}(?:빨갛|벌겋|충혈)",
    "말초부종": r"손끝|발끝|반지가\s*꽉|말초부종",
    "목소리 변화": r"목소리.{0,10}(?:쉬|잠겨|안\s*나와)",
    "목의 통증": r"목.{0,8}(?:칼칼|따갑|아프|아픈|아파|아퍼|아푸)|인후통",
    "발한": r"식은땀|땀(?:이|을)?\s*자꾸|발한",
    "복부 통증": r"배.{0,8}(?:아프|아픈|아파|아퍼)|복부\s*통증",
    "복부팽만감": r"배.{0,8}(?:빵빵|더부룩)|복부팽만",
    "부정맥": r"맥.{0,8}(?:고르지|건너뛰|들쑥날쑥|툭\s*빠지)|부정맥",
    "불안": r"불안|마음이.{0,12}걱정",
    "빈맥": r"심장.{0,10}빨리\s*뛰|너무\s*빨리\s*뛰|빈맥",
    "사래걸림": r"사[래레](?:가|를|에)?|사[래레]\s*들",
    "사지 부종": r"손발.{0,8}붓|사지\s*부종",
    "삼키기 곤란": r"삼키.{0,12}(?:안\s*넘어|힘들|곤란)|목에\s*걸린.{0,10}안\s*넘어",
    "설사": r"설사|화장실을\s*자꾸",
    "식욕부진": r"입맛.{0,6}없|식욕\s*부진",
    "어지러움": r"어지|핑\s*돌",
    "열": r"열(?:이|은)?\s*(?:나|올라|있)|다시\s*올라|발열",
    "오한": r"으슬으슬|춥|추워|오한",
    "온몸이 떨림": r"덜덜\s*떨|온몸.{0,6}떨",
    "운동 시 호흡곤란": r"(?:계단|걸을|움직).{0,14}숨.{0,6}차|조금만\s*움직여도\s*숨",
    "재채기": r"재채기",
    "천명음": r"쌕쌕|천명",
    "창백": r"핏기.{0,8}빠진|창백",
    "콧물": r"콧물|코물|훌쩍",
    "코막힘": r"코.{0,5}(?:막|맥혀)",
    "피로감": r"피곤|더\s*피곤|누워\s*있고\s*싶",
    "하지부종": r"다리.{0,8}붓|다리.{0,8}퉁퉁|신발이\s*꽉",
    "호흡곤란": r"숨.{0,5}(?:차|벅차|막히|가쁘)|숨쉬기.{0,6}갑갑|말하기가.{0,8}힘들",
    "화농성 객담": r"누런\s*가래|가래.{0,8}(?:누렇|진하)",
    "흉통": r"가[슴심].{0,14}(?:콕콕|찌르|결리|아프|아픈|아파|아퍼)",
}


ALERT_SYMPTOMS = {
    "객혈",
    "가슴 답답",
    "호흡곤란",
    "운동 시 호흡곤란",
    "흉통",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cases_by_id(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in cases}


def assert_training_integrity(cases: list[dict[str, Any]], symptom_index: dict[str, Any]) -> None:
    if len(cases) != 100:
        raise RuntimeError(f"Expected 100 training cases, got {len(cases)}")
    if len({case["case_id"] for case in cases}) != len(cases):
        raise RuntimeError("Duplicate case_id in train_100")
    if len({case["text"] for case in cases}) != len(cases):
        raise RuntimeError("Duplicate patient text in train_100")
    golds = {symptom for case in cases for symptom in case["gold_symptoms"]}
    missing = sorted(golds - set(symptom_index))
    if missing:
        raise RuntimeError(f"Gold symptoms missing from symptom_index: {missing}")
    unmapped = sorted(golds - set(SLOT_BY_SYMPTOM))
    if unmapped:
        raise RuntimeError(f"Gold symptoms missing slot mapping: {unmapped}")
    for symptom in golds:
        if symptom not in KEYWORDS_BY_SYMPTOM or symptom not in ALIAS_PATTERNS:
            raise RuntimeError(f"Symptom missing keyword/alias definition: {symptom}")
    for symptom, pattern in ALIAS_PATTERNS.items():
        if symptom in golds:
            re.compile(pattern)


def build_domain_pack(cases: list[dict[str, Any]]) -> dict[str, Any]:
    gold_counts = Counter(symptom for case in cases for symptom in case["gold_symptoms"])
    symptoms = sorted(gold_counts, key=lambda name: (SLOT_BY_SYMPTOM[name], name))
    case_ids_by_symptom: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        for symptom in case["gold_symptoms"]:
            case_ids_by_symptom[symptom].append(case["case_id"])

    symptom_rules = [
        {
            "name": symptom,
            "slot_id": SLOT_BY_SYMPTOM[symptom],
            "keywords": KEYWORDS_BY_SYMPTOM[symptom],
            "alert": symptom in ALERT_SYMPTOMS,
            "train_case_ids": case_ids_by_symptom[symptom],
        }
        for symptom in symptoms
    ]

    ir_text_aliases = [
        {
            "pattern": ALIAS_PATTERNS[symptom],
            "canonical_name": symptom,
            "train_case_ids": case_ids_by_symptom[symptom],
        }
        for symptom in symptoms
    ]

    symptom_quote_patterns = {
        SLOT_BY_SYMPTOM[symptom]: [ALIAS_PATTERNS[symptom]]
        for symptom in symptoms
    }

    return {
        "version": "respiratory-train100-v1",
        "description": "문진톡톡 MVP respiratory domain pack rebuilt from clean train_100 only.",
        "ir_source_id": "respiratory",
        "fewshot_id": "respiratory",
        "fewshot_sets": {
            "extraction": "fewshots/respiratory/extraction.json",
            "standardization": "fewshots/respiratory/standardization.json",
            "semantic_unit": "fewshots/respiratory/semantic_unit.json",
            "span_tagging": "fewshots/respiratory/span_tagging.json",
            "symptom_hint": "fewshots/respiratory/symptom_hint.json",
            "onepager_review": "fewshots/respiratory/onepager_review.json",
        },
        "training_provenance": {
            "source_cases": "evaluation/generated/train_100/cases.jsonl",
            "case_count": len(cases),
            "unique_gold_symptom_count": len(symptoms),
            "test_data_used": False,
            "build_script": "evaluation/train_100_training/build_train_artifacts.py",
        },
        "excluded_ir_symptom_names": ["사망", "무증상"],
        "alert_slot_ids": [SLOT_BY_SYMPTOM[symptom] for symptom in sorted(ALERT_SYMPTOMS)],
        "reviewer_domain_rules": {
            "rule5": "5. Do NOT add fever/temperature tasks unless fever, heat, chill, high fever, antipyretic use, or body temperature appears in evidence.",
            "rule6": "6. Do NOT add X-ray, TB, pneumonia, cancer, antibiotics, or lab/test tasks unless safety_flags, patient wording, or clinician agenda explicitly supports them.",
            "rule11_suffix": "Ordinary sore throat, nasal obstruction, cough, runny nose, or nasal congestion must not be marked urgent.",
        },
        "symptom_rules": symptom_rules,
        "symptom_quote_patterns": symptom_quote_patterns,
        "ir_stable_slot_ids": {symptom: SLOT_BY_SYMPTOM[symptom] for symptom in symptoms},
        "ir_slot_to_canonical_name": {SLOT_BY_SYMPTOM[symptom]: symptom for symptom in symptoms},
        "ir_text_aliases": ir_text_aliases,
        "ir_red_flag_names": sorted(ALERT_SYMPTOMS),
        "safety_flags": [
            {
                "category": "hemoptysis",
                "label": "객혈 의심",
                "severity": "high",
                "pattern": r"피가\s*(?:조금\s*)?(?:섞여|비쳐|보여|나왔)|피\s*섞|피가래|객혈",
            },
            {
                "category": "dyspnea",
                "label": "호흡곤란",
                "severity": "high",
                "pattern": r"숨.{0,5}(?:차|벅차|막히|가쁘)|숨쉬기.{0,6}갑갑|말하기가.{0,8}힘들",
            },
            {
                "category": "exertional_dyspnea",
                "label": "운동 시 호흡곤란",
                "severity": "high",
                "pattern": r"(?:계단|걸을|움직).{0,14}숨.{0,6}차|조금만\s*움직여도\s*숨",
            },
            {
                "category": "chest_pain",
                "label": "흉통",
                "severity": "high",
                "pattern": r"가[슴심].{0,12}(?:콕콕|찌르|결리|아파)",
            },
            {
                "category": "chest_discomfort",
                "label": "가슴 답답",
                "severity": "high",
                "pattern": r"가[슴심].{0,6}(?:답답|꽉\s*막)",
            },
        ],
        "agenda_category_rules": [
            {"pattern": r"같이\s*먹|함께\s*먹|병용", "category": "drug_drug_interaction"},
            {"pattern": r"언제까지|며칠|얼마나", "category": "treatment_duration"},
            {"pattern": r"검사|촬영|엑스레이|CT", "category": "test_question"},
        ],
    }


def case(case_map: dict[str, dict[str, Any]], case_id: str) -> dict[str, Any]:
    return case_map[case_id]


def build_fewshots(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id = cases_by_id(cases)
    return {
        "extraction": extraction_fewshots(by_id),
        "standardization": standardization_fewshots(by_id),
        "semantic_unit": semantic_unit_fewshots(by_id),
        "span_tagging": span_tagging_fewshots(by_id),
        "symptom_hint": symptom_hint_fewshots(by_id),
        "onepager_review": onepager_review_fewshots(),
    }


def extraction_fewshots(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    c1 = case(by_id, "train_bp_001")
    c2 = case(by_id, "train_bp_010")
    c3 = case(by_id, "train_bp_012")
    c4 = case(by_id, "train_bp_051")
    c5 = case(by_id, "train_bp_066")
    c6 = case(by_id, "train_bp_087")
    return {
        "version": "respiratory-extraction-train100-v1",
        "stage": "extraction",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": [
            {
                "title": "Q1 split current throat pain and nasal obstruction",
                "source_case_id": c1["case_id"],
                "visit_type": "initial",
                "question_id": "Q1",
                "question_type": "chief_complaint",
                "patient_answer": c1["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "목이 칼칼하고",
                            "type": "symptom",
                            "slot_ref": "sore_throat",
                            "name": "목 칼칼함",
                            "normalized_text": "목이 칼칼합니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "목의 칼칼함을 현재 증상으로 말했습니다.",
                        },
                        {
                            "source_quote": "코가 꽉 막혀",
                            "type": "symptom",
                            "slot_ref": "nasal_obstruction",
                            "name": "코막힘",
                            "normalized_text": "코가 꽉 막혀 있습니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "코막힘을 현재 증상으로 말했습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "어제부터 목이 칼칼하고 코가 꽉 막혔습니다.",
                        "clinical_clues": [
                            {
                                "category": "증상맥락",
                                "label": "시작시점",
                                "summary": "어제부터 증상이 시작되었습니다.",
                                "source_quote": "어제부터",
                                "source_question": "Q1",
                                "priority": "일반",
                                "related_symptoms": ["목의 통증", "코막힘"],
                            }
                        ],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
            {
                "title": "Q1 colored sputum without hemoptysis",
                "source_case_id": c2["case_id"],
                "visit_type": "initial",
                "question_id": "Q1",
                "question_type": "chief_complaint",
                "patient_answer": c2["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "가래가 누렇고 진하게 나오는데",
                            "type": "symptom",
                            "slot_ref": "purulent_sputum",
                            "name": "누렇고 진한 가래",
                            "normalized_text": "누렇고 진한 가래가 나옵니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "가래의 색과 농도가 현재 증상으로 언급되었습니다.",
                        },
                        {
                            "source_quote": "피가 섞이진 않았어",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "객혈 없음",
                            "normalized_text": "피가 섞인 가래는 없습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "피 섞임을 명시적으로 부정했습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "가래가 누렇고 진하게 나오지만 피가 섞이지는 않았습니다.",
                        "clinical_clues": [],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
            {
                "title": "Q1 dyspnea remains active while chest pain is denied",
                "source_case_id": c3["case_id"],
                "visit_type": "initial",
                "question_id": "Q1",
                "question_type": "chief_complaint",
                "patient_answer": c3["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "숨이 차서 말하기가 좀 힘든데",
                            "type": "symptom",
                            "slot_ref": "dyspnea",
                            "name": "말하기 힘든 숨참",
                            "normalized_text": "숨이 차서 말하기가 조금 힘듭니다.",
                            "status": "있음",
                            "alert": True,
                            "explain": "숨참이 현재 증상으로 언급되었습니다.",
                        },
                        {
                            "source_quote": "가슴이 아프진 않아",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "흉통 없음",
                            "normalized_text": "가슴 통증은 없습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "가슴 통증을 부정했습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "숨이 차서 말하기가 조금 힘들지만 가슴 통증은 없습니다.",
                        "clinical_clues": [],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
            {
                "title": "Q3 resolved old symptom plus persistent current symptom",
                "source_case_id": c4["case_id"],
                "visit_type": "followup",
                "question_id": "Q3",
                "question_type": "new_symptoms",
                "patient_answer": c4["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "지난번 목 아픈 건 좀 나았는데",
                            "type": "progress_improved",
                            "slot_ref": "other",
                            "name": "목 통증 호전",
                            "normalized_text": "지난번 목 통증은 조금 나았습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "이전 증상이 호전된 경과입니다.",
                        },
                        {
                            "source_quote": "코막힘은 아직 있어",
                            "type": "progress_unchanged",
                            "slot_ref": "nasal_obstruction",
                            "name": "지속되는 코막힘",
                            "normalized_text": "코막힘은 아직 있습니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "코막힘이 현재 남아 있습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "지난번 목 통증은 조금 나았지만 코막힘은 아직 있습니다.",
                        "clinical_clues": [],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
            {
                "title": "Q3 muscle weakness is not generic fatigue",
                "source_case_id": c5["case_id"],
                "visit_type": "followup",
                "question_id": "Q3",
                "question_type": "new_symptoms",
                "patient_answer": c5["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "그냥 피곤한 게 아니라",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "단순 피로감 아님",
                            "normalized_text": "단순한 피로감은 아니라고 말했습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "피로감을 주 증상으로 부정했습니다.",
                        },
                        {
                            "source_quote": "팔다리에 힘이 잘 안 들어가",
                            "type": "new",
                            "slot_ref": "muscle_weakness",
                            "name": "팔다리 근력 약화",
                            "normalized_text": "팔다리에 힘이 잘 들어가지 않습니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "팔다리 힘 저하가 새 증상으로 언급되었습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "단순히 피곤한 것이 아니라 팔다리에 힘이 잘 들어가지 않습니다.",
                        "clinical_clues": [],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
            {
                "title": "Q3 dialect chest pain with dyspnea denied",
                "source_case_id": c6["case_id"],
                "visit_type": "followup",
                "question_id": "Q3",
                "question_type": "new_symptoms",
                "patient_answer": c6["text"],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "가심이 새로 아픈데",
                            "type": "new",
                            "slot_ref": "chest_pain",
                            "name": "새로 생긴 가슴 통증",
                            "normalized_text": "가슴 통증이 새로 생겼습니다.",
                            "status": "있음",
                            "alert": True,
                            "explain": "강원 구어 '가심'은 가슴 의미이며 통증을 현재 증상으로 말했습니다.",
                        },
                        {
                            "source_quote": "숨찬 건 아녀",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "숨참 없음",
                            "normalized_text": "숨찬 느낌은 없습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "숨참을 부정했습니다.",
                        },
                    ],
                    "structured": {
                        "standardized_text": "가슴 통증이 새로 생겼지만 숨찬 느낌은 아닙니다.",
                        "clinical_clues": [],
                        "questions": [],
                        "unresolved_items": [],
                    },
                },
            },
        ],
    }


def standardization_fewshots(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [
        ("train_bp_027", "코가 꽉 막혀서 숨쉬기 답답해", ["맥혀를 막혀로 표준화", "갑갑해를 답답해로 표준화"]),
        ("train_bp_039", "가슴 한쪽이 결리듯 아파서 왔어", ["가심을 가슴으로 표준화"]),
        ("train_bp_049", "설사를 자꾸 하는데 토하는 건 아니야", ["아녀를 아니야로 표준화"]),
        ("train_bp_077", "코가 아직도 막혀서 답답해", ["맥혀를 막혀로 표준화"]),
        ("train_bp_087", "가슴이 새로 아픈데 숨찬 건 아니야", ["가심을 가슴으로 표준화", "아녀를 아니야로 표준화"]),
    ]
    return {
        "version": "respiratory-standardization-train100-v1",
        "stage": "standardization",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": [
            {
                "title": f"standardize train case {case_id}",
                "source_case_id": case_id,
                "input": by_id[case_id]["text"],
                "expected_json": {
                    "standardized_text": standardized,
                    "normalization_notes": notes,
                },
            }
            for case_id, standardized, notes in rows
        ],
    }


def semantic_unit_fewshots(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    examples = [
        {
            "title": "split resolved symptom and persistent symptom",
            "source_case_id": "train_bp_051",
            "original": by_id["train_bp_051"]["text"],
            "standardized": "지난번 목 통증은 조금 나았지만 코막힘은 아직 있습니다.",
            "expected_json": {
                "meaning_units": [
                    {"source_quote": "지난번 목 아픈 건 좀 나았는데", "normalized_text": "지난번 목 통증은 조금 나았습니다.", "role": "clinical_meaning"},
                    {"source_quote": "코막힘은 아직 있어", "normalized_text": "코막힘은 아직 있습니다.", "role": "clinical_meaning"},
                ],
                "clinical_clues": [],
                "questions": [],
                "unresolved_items": [],
            },
        },
        {
            "title": "split active symptom and denied symptom",
            "source_case_id": "train_bp_012",
            "original": by_id["train_bp_012"]["text"],
            "standardized": "숨이 차서 말하기가 조금 힘들지만 가슴 통증은 없습니다.",
            "expected_json": {
                "meaning_units": [
                    {"source_quote": "숨이 차서 말하기가 좀 힘든데", "normalized_text": "숨이 차서 말하기가 조금 힘듭니다.", "role": "clinical_meaning"},
                    {"source_quote": "가슴이 아프진 않아", "normalized_text": "가슴 통증은 없습니다.", "role": "clinical_meaning"},
                ],
                "clinical_clues": [],
                "questions": [],
                "unresolved_items": [],
            },
        },
        {
            "title": "do not merge fatigue denial with weakness",
            "source_case_id": "train_bp_066",
            "original": by_id["train_bp_066"]["text"],
            "standardized": "단순히 피곤한 것이 아니라 팔다리에 힘이 잘 들어가지 않습니다.",
            "expected_json": {
                "meaning_units": [
                    {"source_quote": "그냥 피곤한 게 아니라", "normalized_text": "단순한 피로감은 아니라고 말했습니다.", "role": "clinical_meaning"},
                    {"source_quote": "팔다리에 힘이 잘 안 들어가", "normalized_text": "팔다리에 힘이 잘 들어가지 않습니다.", "role": "clinical_meaning"},
                ],
                "clinical_clues": [],
                "questions": [],
                "unresolved_items": [],
            },
        },
    ]
    return {
        "version": "respiratory-semantic-unit-train100-v1",
        "stage": "semantic_unit",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": examples,
    }


def span_tagging_fewshots(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "respiratory-span-tagging-train100-v1",
        "stage": "span_tagging",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": [
            {
                "title": "active current symptom",
                "source_case_id": "train_bp_014",
                "meaning_units": [{"source_quote": "가슴이 꽉 막힌 것처럼 답답해", "normalized_text": "가슴이 꽉 막힌 것처럼 답답합니다.", "role": "clinical_meaning"}],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "가슴이 꽉 막힌 것처럼 답답해",
                            "type": "symptom",
                            "slot_ref": "other",
                            "name": "가슴 답답함",
                            "normalized_text": "가슴이 꽉 막힌 것처럼 답답합니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "현재 증상입니다.",
                        }
                    ]
                },
            },
            {
                "title": "denied symptom stays inactive",
                "source_case_id": "train_bp_010",
                "meaning_units": [{"source_quote": "피가 섞이진 않았어", "normalized_text": "피가 섞이지는 않았습니다.", "role": "clinical_meaning"}],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "피가 섞이진 않았어",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "객혈 없음",
                            "normalized_text": "피가 섞이지는 않았습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "증상을 부정했습니다.",
                        }
                    ]
                },
            },
            {
                "title": "resolved previous symptom is not active",
                "source_case_id": "train_bp_052",
                "meaning_units": [{"source_quote": "열은 다 내렸는데", "normalized_text": "열은 다 내렸습니다.", "role": "clinical_meaning"}],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "열은 다 내렸는데",
                            "type": "progress_improved",
                            "slot_ref": "other",
                            "name": "열 호전",
                            "normalized_text": "열은 다 내렸습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "이전 증상이 호전된 경과입니다.",
                        }
                    ]
                },
            },
            {
                "title": "new interval symptom",
                "source_case_id": "train_bp_060",
                "meaning_units": [{"source_quote": "진료 이후로 조금만 걸어도 숨이 차기 시작했어", "normalized_text": "진료 이후 조금만 걸어도 숨이 차기 시작했습니다.", "role": "clinical_meaning"}],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "진료 이후로 조금만 걸어도 숨이 차기 시작했어",
                            "type": "new",
                            "slot_ref": "other",
                            "name": "걸을 때 숨참",
                            "normalized_text": "진료 이후 조금만 걸어도 숨이 차기 시작했습니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "진료 이후 새로 생긴 증상입니다.",
                        }
                    ]
                },
            },
        ],
    }


def symptom_hint_fewshots(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "respiratory-symptom-hint-train100-v1",
        "stage": "symptom_hint",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": [
            {
                "title": "colored sputum maps to purulent sputum",
                "source_case_id": "train_bp_010",
                "tagged_spans": [
                    {
                        "source_quote": "가래가 누렇고 진하게 나오는데",
                        "type": "symptom",
                        "slot_ref": "other",
                        "name": "누렇고 진한 가래",
                        "normalized_text": "누렇고 진한 가래가 나옵니다.",
                        "status": "있음",
                        "alert": False,
                        "explain": "현재 증상입니다.",
                    }
                ],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "가래가 누렇고 진하게 나오는데",
                            "type": "symptom",
                            "slot_ref": "purulent_sputum",
                            "name": "누렇고 진한 가래",
                            "normalized_text": "누렇고 진한 가래가 나옵니다.",
                            "status": "있음",
                            "alert": False,
                            "explain": "가래 색과 농도를 검색 힌트에 보존했습니다.",
                        }
                    ]
                },
            },
            {
                "title": "chest tightness maps to chest discomfort",
                "source_case_id": "train_bp_014",
                "tagged_spans": [
                    {
                        "source_quote": "가슴이 꽉 막힌 것처럼 답답해",
                        "type": "symptom",
                        "slot_ref": "other",
                        "name": "답답함",
                        "normalized_text": "가슴이 꽉 막힌 것처럼 답답합니다.",
                        "status": "있음",
                        "alert": False,
                        "explain": "현재 증상입니다.",
                    }
                ],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "가슴이 꽉 막힌 것처럼 답답해",
                            "type": "symptom",
                            "slot_ref": "chest_discomfort",
                            "name": "가슴 답답함",
                            "normalized_text": "가슴이 꽉 막힌 것처럼 답답합니다.",
                            "status": "있음",
                            "alert": True,
                            "explain": "위치가 가슴인 답답함이므로 가슴 답답으로 검색합니다.",
                        }
                    ]
                },
            },
            {
                "title": "exercise-related dyspnea stays specific",
                "source_case_id": "train_bp_086",
                "tagged_spans": [
                    {
                        "source_quote": "걸을 때마다 숨이 벅차게 차기 시작했어",
                        "type": "new",
                        "slot_ref": "other",
                        "name": "숨참",
                        "normalized_text": "걸을 때마다 숨이 벅차게 차기 시작했습니다.",
                        "status": "있음",
                        "alert": False,
                        "explain": "새 증상입니다.",
                    }
                ],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "걸을 때마다 숨이 벅차게 차기 시작했어",
                            "type": "new",
                            "slot_ref": "exertional_dyspnea",
                            "name": "걸을 때 숨참",
                            "normalized_text": "걸을 때마다 숨이 벅차게 차기 시작했습니다.",
                            "status": "있음",
                            "alert": True,
                            "explain": "활동 시 숨참이라는 구체성을 유지했습니다.",
                        }
                    ]
                },
            },
            {
                "title": "negative symptom remains inactive",
                "source_case_id": "train_bp_087",
                "tagged_spans": [
                    {
                        "source_quote": "숨찬 건 아녀",
                        "type": "symptom_absent",
                        "slot_ref": "other",
                        "name": "숨참",
                        "normalized_text": "숨찬 느낌은 없습니다.",
                        "status": "없음",
                        "alert": False,
                        "explain": "부정된 증상입니다.",
                    }
                ],
                "expected_json": {
                    "spans": [
                        {
                            "source_quote": "숨찬 건 아녀",
                            "type": "symptom_absent",
                            "slot_ref": "other",
                            "name": "숨참 없음",
                            "normalized_text": "숨찬 느낌은 없습니다.",
                            "status": "없음",
                            "alert": False,
                            "explain": "부정된 증상을 active slot으로 바꾸지 않습니다.",
                        }
                    ]
                },
            },
        ],
    }


def onepager_review_fewshots() -> dict[str, Any]:
    return {
        "version": "respiratory-onepager-review-train100-v1",
        "stage": "onepager_review",
        "source_dataset": "evaluation/generated/train_100/cases.jsonl",
        "examples": [
            {
                "title": "red flag symptom creates prioritized review item",
                "input": {
                    "symptom_slots": [{"name": "호흡곤란", "status": "있음", "source_quote": "숨이 차서 말하기가 좀 힘든데"}],
                    "agenda": [],
                    "safety_flags": [{"category": "dyspnea", "label": "호흡곤란", "severity": "high"}],
                },
                "expected_json": {
                    "review_items": ["[우선] 숨참 정도, 안정 시 여부, 흉통/청색증 동반 여부 확인"],
                    "transfer_text": "S) 호흡곤란. 말하기 힘든 숨참 호소. 확인: 안정 시 호흡곤란, 흉통, 청색증 동반 여부.",
                    "doctor_brief": {"headline": "호흡곤란 우선 확인 필요", "sections": []},
                    "issues": [],
                },
            },
            {
                "title": "non-red-flag upper airway symptoms stay routine",
                "input": {
                    "symptom_slots": [
                        {"name": "목의 통증", "status": "있음", "source_quote": "목이 칼칼하고"},
                        {"name": "코막힘", "status": "있음", "source_quote": "코가 꽉 막혀"},
                    ],
                    "agenda": [],
                    "safety_flags": [],
                },
                "expected_json": {
                    "review_items": ["목 통증과 코막힘 지속기간 및 동반 증상 확인"],
                    "transfer_text": "S) 목의 통증, 코막힘. 확인: 지속기간, 발열/기침 동반 여부.",
                    "doctor_brief": {"headline": "상기도 증상 확인 필요", "sections": []},
                    "issues": [],
                },
            },
        ],
    }


def build_report(cases: list[dict[str, Any]], domain_pack: dict[str, Any], fewshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "train100-training-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(TRAIN_CASES_PATH.relative_to(ROOT)).replace("\\", "/"),
        "test_data_used": False,
        "case_count": len(cases),
        "unique_gold_symptom_count": len(domain_pack["ir_stable_slot_ids"]),
        "distribution": {
            "visit_question": dict(Counter(f"{case['visit_type']}_{case['question_id']}" for case in cases)),
            "dialect_type": dict(Counter(case["dialect_type"] for case in cases)),
            "symptom_group": dict(Counter(case["symptom_group"] for case in cases)),
        },
        "outputs": {
            "domain_pack": str(DOMAIN_PACK_PATH.relative_to(ROOT)).replace("\\", "/"),
            "fewshot_dir": str(FEWSHOT_DIR.relative_to(ROOT)).replace("\\", "/"),
        },
        "fewshot_counts": {
            stage: len(payload.get("examples", []))
            for stage, payload in fewshots.items()
        },
        "symptoms": {
            symptom: {
                "slot_id": slot_id,
                "train_count": len([
                    case for case in cases if symptom in case["gold_symptoms"]
                ]),
            }
            for symptom, slot_id in domain_pack["ir_stable_slot_ids"].items()
        },
    }


def main() -> None:
    cases = read_jsonl(TRAIN_CASES_PATH)
    symptom_index = json.loads(SYMPTOM_INDEX_PATH.read_text(encoding="utf-8"))
    assert_training_integrity(cases, symptom_index)

    domain_pack = build_domain_pack(cases)
    fewshots = build_fewshots(cases)
    report = build_report(cases, domain_pack, fewshots)

    write_json(DOMAIN_PACK_PATH, domain_pack)
    for stage, payload in fewshots.items():
        write_json(FEWSHOT_DIR / f"{stage}.json", payload)
    write_json(REPORT_PATH, report)

    print(f"wrote {DOMAIN_PACK_PATH.relative_to(ROOT)}")
    print(f"wrote {FEWSHOT_DIR.relative_to(ROOT)}/*.json")
    print(f"wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"cases={len(cases)} symptoms={len(domain_pack['ir_stable_slot_ids'])}")


if __name__ == "__main__":
    main()
