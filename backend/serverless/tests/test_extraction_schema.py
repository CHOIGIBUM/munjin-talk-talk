"""extraction_schema.py 핵심 검증 함수 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from extraction_schema import (
    empty_structured,
    is_negative_symptom_answer,
    normalize_extraction_output,
    validate_question_level_requirements,
    validate_span_state_consistency,
)


# --- is_negative_symptom_answer ---

def test_negative_answer_patterns():
    assert is_negative_symptom_answer("없어요") is True
    assert is_negative_symptom_answer("아니요") is True
    assert is_negative_symptom_answer("괜찮아요") is True
    assert is_negative_symptom_answer("아픈 거 없어요") is True


def test_positive_answer_not_negative():
    assert is_negative_symptom_answer("기침이 나요") is False
    assert is_negative_symptom_answer("목이 아파요") is False


def test_empty_is_not_negative():
    assert is_negative_symptom_answer("") is False
    assert is_negative_symptom_answer(None) is False


# --- empty_structured ---

def test_empty_structured_shape():
    result = empty_structured("원본 텍스트")
    assert result["standardized_text"] == "원본 텍스트"
    assert result["clinical_clues"] == []
    assert result["questions"] == []
    assert result["unresolved_items"] == []


# --- validate_question_level_requirements ---

def test_symptom_question_with_no_spans_fails():
    normalized = {"spans": [], "structured": {"standardized_text": "기침이 나요"}}
    errors = validate_question_level_requirements(normalized, "기침이 나요", "chief_complaint")
    assert len(errors) > 0
    assert "spans" in errors[0]["loc"]


def test_non_symptom_question_with_no_spans_passes():
    normalized = {"spans": [], "structured": {"standardized_text": "질문 없습니다"}}
    errors = validate_question_level_requirements(normalized, "질문 없습니다", "patient_questions")
    assert errors == []


def test_negative_transcript_allows_empty_spans():
    normalized = {"spans": [], "structured": {"standardized_text": "없어요"}}
    errors = validate_question_level_requirements(normalized, "없어요", "chief_complaint")
    assert errors == []


# --- validate_span_state_consistency ---

def test_non_active_span_must_have_absent_status():
    normalized = {
        "spans": [
            {"type": "progress_improved", "status": "있음"},
        ]
    }
    errors = validate_span_state_consistency(normalized)
    assert len(errors) > 0
    assert "status" in errors[0]["loc"]


def test_non_active_span_with_absent_status_passes():
    normalized = {
        "spans": [
            {"type": "progress_improved", "status": "없음"},
        ]
    }
    errors = validate_span_state_consistency(normalized)
    assert errors == []


def test_active_span_cannot_have_absent_status():
    normalized = {
        "spans": [
            {"type": "symptom", "status": "없음"},
        ]
    }
    errors = validate_span_state_consistency(normalized)
    assert len(errors) > 0
    assert "type" in errors[0]["loc"]


def test_active_span_with_present_status_passes():
    normalized = {
        "spans": [
            {"type": "symptom", "status": "있음"},
        ]
    }
    errors = validate_span_state_consistency(normalized)
    assert errors == []


# --- normalize_extraction_output ---

def test_valid_extraction_passes():
    transcript = "기침이 계속 나요"
    obj = {
        "spans": [
            {
                "source_quote": "기침이 계속 나요",
                "type": "symptom",
                "slot_ref": "cough",
                "name": "기침",
                "normalized_text": "기침이 지속됨",
                "status": "있음",
                "alert": False,
                "explain": "환자가 기침 지속을 말했습니다.",
            }
        ],
        "structured": {
            "standardized_text": "기침이 계속 납니다.",
            "clinical_clues": [],
            "questions": [],
            "unresolved_items": [],
        },
    }
    normalized, errors = normalize_extraction_output(obj, transcript, "Q1", "chief_complaint")
    assert errors == []
    assert normalized["spans"][0]["slot_ref"] == "cough"


def test_extraction_with_ungrounded_quote_fails():
    transcript = "기침이 나요"
    obj = {
        "spans": [
            {
                "source_quote": "완전히 다른 말",
                "type": "symptom",
                "slot_ref": "cough",
                "name": "기침",
                "normalized_text": "기침",
                "status": "있음",
                "alert": False,
                "explain": "환자가 기침을 말했습니다.",
            }
        ],
        "structured": {
            "standardized_text": transcript,
            "clinical_clues": [],
            "questions": [],
            "unresolved_items": [],
        },
    }
    normalized, errors = normalize_extraction_output(obj, transcript, "Q1", "chief_complaint")
    assert len(errors) > 0
