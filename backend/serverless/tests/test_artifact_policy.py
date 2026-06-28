"""artifact_policy.py 운영 저장 정리 정책 테스트.

S3에 저장하기 전 민감/불필요 필드가 제거되는지, 화면에 필요한 필드는
보존되는지 검증합니다.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from artifact_policy import (
    ANSWER_FILE,
    GUIDE_FILE,
    ONEPAPER_FILE,
    TRACE_FILE,
    keep_keys,
    normalize_scalar,
    prepare_artifact_payload,
    sanitize_answers,
    sanitize_matched_slot,
    sanitize_onepaper,
    sanitize_span,
    sanitize_structured,
)


# --- keep_keys ---

def test_keep_keys_only_allowed():
    src = {"a": 1, "b": 2, "secret": 3}
    assert keep_keys(src, ["a", "b"]) == {"a": 1, "b": 2}
    assert "secret" not in keep_keys(src, ["a", "b"])


def test_keep_keys_missing_ignored():
    assert keep_keys({"a": 1}, ["a", "x"]) == {"a": 1}


# --- normalize_scalar ---

def test_normalize_scalar_decimal_to_float():
    assert normalize_scalar(Decimal("3.14")) == 3.14


def test_normalize_scalar_passthrough():
    assert normalize_scalar("text") == "text"
    assert normalize_scalar(42) == 42
    assert normalize_scalar(True) is True
    assert normalize_scalar(None) is None


def test_normalize_scalar_truncates_long_list():
    long_list = list(range(50))
    assert len(normalize_scalar(long_list)) == 10


# --- sanitize_span ---

def test_sanitize_span_keeps_allowed_drops_scores():
    span = {
        "source_quote": "기침이 나요",
        "type": "symptom",
        "slot_ref": "cough",
        "name": "기침",
        "normalized_text": "기침",
        "status": "있음",
        "alert": False,
        "explain": "설명",
        "confidence": 0.9,    # 제거되어야 함
        "rank_score": 1.2,    # 제거되어야 함
    }
    cleaned = sanitize_span(span)
    assert cleaned["name"] == "기침"
    assert "confidence" not in cleaned
    assert "rank_score" not in cleaned


# --- sanitize_matched_slot ---

def test_sanitize_matched_slot_removes_numeric_and_trace():
    slot = {
        "slot_id": "cough",
        "name": "기침",
        "source_quote": "기침이 나요",
        "status": "있음",
        "ir_method": "bm25_titan_hybrid",
        "score": 0.91,
        "rank_score": 1.28,
        "ir_trace": {"top_candidates": [{"name": "기침"}]},
        "bm25_score": 0.5,
        "vector_score": 0.6,
    }
    cleaned = sanitize_matched_slot(slot)
    assert cleaned["slot_id"] == "cough"
    assert cleaned["ir_method"] == "bm25_titan_hybrid"
    for forbidden in ("score", "rank_score", "ir_trace", "bm25_score", "vector_score"):
        assert forbidden not in cleaned, f"{forbidden}가 제거되지 않음"


# --- sanitize_structured ---

def test_sanitize_structured_shape():
    structured = {
        "standardized_text": "  기침이 납니다.  ",
        "clinical_clues": [{"category": "c", "summary": "s", "secret": "x"}],
        "questions": [{"category": "q", "summary": "qs", "extra": "y"}],
        "unresolved_items": [{"a": 1}],
    }
    cleaned = sanitize_structured(structured)
    assert cleaned["standardized_text"] == "기침이 납니다"
    assert "secret" not in cleaned["clinical_clues"][0]
    assert "extra" not in cleaned["questions"][0]


def test_sanitize_structured_non_dict():
    assert sanitize_structured(None) == {}
    assert sanitize_structured("string") == {}


# --- sanitize_onepaper ---

def test_sanitize_onepaper_keeps_display_fields():
    onepaper = {
        "patient_summary": {"display_name": "홍*동"},
        "symptom_slots": [{"slot_id": "cough", "name": "기침", "score": 0.9}],
        "safety_flags": [],
        "internal_debug": "should be removed",
    }
    cleaned = sanitize_onepaper(onepaper)
    assert "internal_debug" not in cleaned
    assert cleaned["symptom_slots"][0]["name"] == "기침"
    assert "score" not in cleaned["symptom_slots"][0]


# --- sanitize_answers ---

def test_sanitize_answers_structure():
    payload = {
        "Q1": {
            "text": "기침이 나요",
            "spans": [{"source_quote": "기침이 나요", "type": "symptom", "name": "기침", "score": 0.9}],
            "matched_slots": [{"slot_id": "cough", "name": "기침", "rank_score": 1.2}],
            "structured": {"standardized_text": "기침이 납니다"},
        }
    }
    cleaned = sanitize_answers(payload)
    assert "Q1" in cleaned
    assert cleaned["Q1"]["text"] == "기침이 나요"
    assert "score" not in cleaned["Q1"]["spans"][0]
    assert "rank_score" not in cleaned["Q1"]["matched_slots"][0]


def test_sanitize_answers_non_dict():
    assert sanitize_answers(None) == {}
    assert sanitize_answers([]) == {}


# --- prepare_artifact_payload 라우팅 ---

def test_prepare_artifact_routes_by_filename():
    answers = {"Q1": {"text": "기침", "spans": [], "matched_slots": [], "structured": {}}}
    result = prepare_artifact_payload(ANSWER_FILE, answers)
    assert "Q1" in result
    # 알 수 없는 파일명은 deepcopy로 통과
    other = prepare_artifact_payload("unknown.json", {"a": 1})
    assert other == {"a": 1}


def test_prepare_artifact_trace_removes_prompts():
    trace = {
        "Q1": {
            "active_path": ["input_transcript", "semantic_extraction"],
            "events": [{"node": "x", "status": "passed", "details": {"prompt": "secret prompt", "model_id": "nova"}}],
        }
    }
    result = prepare_artifact_payload(TRACE_FILE, trace)
    event_details = result["Q1"]["events"][0]["details"]
    # prompt 전문은 details 허용 목록에 없어 제거, model_id는 유지
    assert "prompt" not in event_details
    assert event_details.get("model_id") == "nova"
