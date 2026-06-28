"""domain_config.py와 question_sets.py 설정 로더 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from domain_config import (
    alert_slot_ids,
    excluded_ir_symptom_names,
    get_domain_pack,
    llm_symptom_slot_ids,
    symptom_slot_ids,
)
from question_sets import (
    ALLOWED_QUESTION_TYPES,
    get_question_set,
    prompt_question_text,
    public_question_set,
    validate_question_set,
)


# --- domain_config ---

def test_domain_pack_loads_required_keys():
    pack = get_domain_pack()
    assert "symptom_rules" in pack
    assert "safety_flags" in pack
    assert "alert_slot_ids" in pack


def test_invalid_domain_pack_id_raises():
    with pytest.raises(RuntimeError, match="Invalid domain pack id"):
        get_domain_pack("../etc/passwd")


def test_missing_domain_pack_raises():
    with pytest.raises(FileNotFoundError):
        get_domain_pack("nonexistent-pack-xyz")


def test_llm_symptom_slot_ids_nonempty():
    ids = llm_symptom_slot_ids()
    assert isinstance(ids, list)
    assert len(ids) > 0
    assert "cough" in ids


def test_symptom_slot_ids_includes_other():
    ids = symptom_slot_ids()
    assert "other" in ids
    assert "cough" in ids


def test_alert_slot_ids_are_tuple():
    ids = alert_slot_ids()
    assert isinstance(ids, tuple)
    # 호흡기 도메인엔 호흡곤란 등 위험 slot이 있어야 함
    assert len(ids) > 0


def test_excluded_ir_symptom_names_is_set():
    names = excluded_ir_symptom_names()
    assert isinstance(names, set)


# --- question_sets ---

def test_default_question_set_structure():
    qs = get_question_set("default")
    assert qs is not None
    assert qs["id"] == "default"
    assert "initial" in qs["visits"]
    assert "followup" in qs["visits"]
    assert qs["visits"]["initial"][0]["id"] == "Q1"


def test_missing_question_set_returns_none():
    assert get_question_set("no-such-set") is None


def test_path_traversal_question_set_returns_none():
    assert get_question_set("../../../etc/passwd") is None


def test_validate_question_set_rejects_bad_type():
    broken = {
        "id": "broken",
        "visits": {
            "initial": [{"id": "Q1", "title": "질문", "question_type": "INVALID"}],
            "followup": [{"id": "Q1", "title": "질문", "question_type": "progress"}],
        },
    }
    with pytest.raises(RuntimeError, match="Invalid question_type"):
        validate_question_set(broken)


def test_validate_question_set_rejects_duplicate_ids():
    broken = {
        "id": "dup",
        "visits": {
            "initial": [
                {"id": "Q1", "title": "질문1", "question_type": "chief_complaint"},
                {"id": "Q1", "title": "질문2", "question_type": "onset"},
            ],
            "followup": [{"id": "Q1", "title": "질문", "question_type": "progress"}],
        },
    }
    with pytest.raises(RuntimeError, match="Duplicate or empty"):
        validate_question_set(broken)


def test_validate_question_set_requires_title():
    broken = {
        "id": "notitle",
        "visits": {
            "initial": [{"id": "Q1", "title": "", "question_type": "chief_complaint"}],
            "followup": [{"id": "Q1", "title": "질문", "question_type": "progress"}],
        },
    }
    with pytest.raises(RuntimeError, match="title is required"):
        validate_question_set(broken)


def test_public_question_set_exposes_minimal_fields():
    public = public_question_set("default")
    assert set(public.keys()) == {"id", "visits"}


def test_prompt_question_text_returns_text_for_known_question():
    text = prompt_question_text("initial", "Q1", "default")
    assert isinstance(text, str)
    assert len(text) > 0


def test_prompt_question_text_unknown_returns_empty():
    assert prompt_question_text("initial", "Q99", "default") == ""
    assert prompt_question_text("initial", "Q1", "no-such-set") == ""


def test_allowed_question_types_contains_core():
    for qtype in ("chief_complaint", "onset", "progress", "patient_questions"):
        assert qtype in ALLOWED_QUESTION_TYPES
