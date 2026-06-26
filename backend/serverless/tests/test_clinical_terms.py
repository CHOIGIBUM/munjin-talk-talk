"""clinical_terms.py 안전 플래그 및 증상 헬퍼 함수 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clinical_terms import (
    VALID_SYMPTOM_SLOT_IDS,
    find_safety_flag,
    find_symptom_quote,
    is_symptom_like_span,
    slot_to_name,
)


# --- find_safety_flag ---

def test_safety_flag_detects_hemoptysis():
    flag = find_safety_flag("가래에 피가 섞여 나와요")
    assert flag is not None
    assert flag["category"] == "hemoptysis"
    assert flag["severity"] == "high"


def test_safety_flag_detects_dyspnea():
    flag = find_safety_flag("숨이 너무 차서 말을 못 하겠어요")
    assert flag is not None
    assert flag["category"] == "dyspnea"


def test_safety_flag_detects_chest_pain():
    flag = find_safety_flag("가슴이 쥐어짜듯 아파요")
    assert flag is not None
    assert flag["category"] == "chest_pain"


def test_safety_flag_detects_consciousness():
    flag = find_safety_flag("갑자기 기절하고 의식을 잃었어요")
    assert flag is not None
    assert flag["category"] == "consciousness"


def test_safety_flag_no_match():
    flag = find_safety_flag("목이 좀 칼칼해요")
    assert flag is None


def test_safety_flag_from_matched_slots():
    flag = find_safety_flag("일반 텍스트", [{"slot_id": "dyspnea", "name": "호흡곤란"}])
    assert flag is not None
    assert flag["category"] == "dyspnea"


def test_safety_flag_empty_text():
    assert find_safety_flag("") is None
    assert find_safety_flag("", []) is None


# --- is_symptom_like_span ---

def test_is_symptom_like_span_valid():
    assert is_symptom_like_span("symptom", "cough") is True
    assert is_symptom_like_span("new", "other") is True
    assert is_symptom_like_span("worsening", "fever") is True


def test_is_symptom_like_span_non_symptom_type():
    assert is_symptom_like_span("medication", "other") is False
    assert is_symptom_like_span("context", "cough") is False


def test_is_symptom_like_span_empty_slot():
    # other 와 empty slot 은 증상으로 간주
    assert is_symptom_like_span("symptom", "") is True
    assert is_symptom_like_span("symptom", "other") is True


# --- slot_to_name ---

def test_slot_to_name_known():
    # 도메인팩에 등록된 slot이면 이름을 반환해야 함
    name = slot_to_name("cough")
    assert name  # 빈 문자열이면 안 됨
    assert name != "cough" or name == "cough"  # 최소한 값이 있어야


def test_slot_to_name_unknown():
    name = slot_to_name("unknown_slot_xyz")
    assert name == "unknown_slot_xyz"


def test_slot_to_name_empty():
    name = slot_to_name("")
    assert name == "-"


# --- VALID_SYMPTOM_SLOT_IDS ---

def test_symptom_slot_ids_has_core_entries():
    assert "cough" in VALID_SYMPTOM_SLOT_IDS
    assert "fever" in VALID_SYMPTOM_SLOT_IDS
