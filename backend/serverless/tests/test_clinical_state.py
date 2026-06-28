"""clinical_state.py 증상 상태 분류 정책 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clinical_state import (
    ABSENT_STATUS,
    PRESENT_STATUS,
    is_absent_symptom_state,
    is_active_symptom_state,
    is_non_active_symptom_state,
    is_progress_improved_state,
    span_status_of,
    span_type_of,
)


# --- span 추출 helper ---

def test_span_type_and_status_safe_extraction():
    assert span_type_of({"type": "symptom"}) == "symptom"
    assert span_type_of(None) == ""
    assert span_type_of({}) == ""
    assert span_status_of({"status": "있음"}) == "있음"
    assert span_status_of(None) == ""


# --- active symptom ---

def test_active_symptom_states():
    assert is_active_symptom_state({"type": "symptom", "status": "있음"}) is True
    assert is_active_symptom_state({"type": "new", "status": "있음"}) is True
    assert is_active_symptom_state({"type": "progress_worsened", "status": "있음"}) is True


def test_active_symptom_with_absent_status_is_not_active():
    # type은 active지만 status가 없음이면 active 아님
    assert is_active_symptom_state({"type": "symptom", "status": ABSENT_STATUS}) is False


def test_non_active_types_are_not_active():
    assert is_active_symptom_state({"type": "progress_improved", "status": "없음"}) is False
    assert is_active_symptom_state({"type": "symptom_absent", "status": "없음"}) is False


# --- non-active symptom ---

def test_non_active_symptom_states():
    assert is_non_active_symptom_state({"type": "progress_improved", "status": "없음"}) is True
    assert is_non_active_symptom_state({"type": "symptom_absent", "status": "없음"}) is True
    # status가 없음이면 type 무관하게 non-active
    assert is_non_active_symptom_state({"type": "symptom", "status": "없음"}) is True


def test_active_symptom_is_not_non_active():
    assert is_non_active_symptom_state({"type": "symptom", "status": "있음"}) is False


# --- progress_improved / absent ---

def test_progress_improved_state():
    assert is_progress_improved_state({"type": "progress_improved"}) is True
    assert is_progress_improved_state({"type": "symptom"}) is False


def test_absent_symptom_state():
    assert is_absent_symptom_state({"type": "symptom_absent"}) is True
    assert is_absent_symptom_state({"type": "symptom", "status": ABSENT_STATUS}) is True
    assert is_absent_symptom_state({"type": "symptom", "status": PRESENT_STATUS}) is False


def test_active_and_non_active_are_mutually_exclusive():
    """active와 non-active는 동시에 참일 수 없어야 합니다."""
    spans = [
        {"type": "symptom", "status": "있음"},
        {"type": "progress_improved", "status": "없음"},
        {"type": "symptom_absent", "status": "없음"},
        {"type": "new", "status": "있음"},
    ]
    for span in spans:
        active = is_active_symptom_state(span)
        non_active = is_non_active_symptom_state(span)
        assert not (active and non_active), f"span이 동시에 active+non-active: {span}"
