"""retrieval.py의 build_symptom_query 및 관련 헬퍼 테스트."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DATA = SRC / "data"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_settings_stub():
    """retrieval 모듈의 settings 의존을 가짜로 주입합니다."""
    for name in [
        "settings",
        "clinical_terms",
        "clinical_state",
        "retrieval_documents",
        "retrieval_embeddings",
        "retrieval",
    ]:
        sys.modules.pop(name, None)
    settings = types.ModuleType("settings")
    settings.DATA_DIR = DATA
    settings.DISEASES_PATH = DATA / "diseases_cleaned.json"
    settings.SYMPTOM_INDEX_PATH = DATA / "symptom_index.json"
    settings.EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
    settings.EMBEDDING_DIMENSIONS = 512
    settings.EMBEDDING_CACHE_PATH = DATA / "symptom_embeddings_amazon.titan-embed-text-v2_0_512.json"
    settings.HYBRID_TOP_K = 5
    settings.HYBRID_CANDIDATE_K = 24
    settings.HYBRID_ACCEPT_THRESHOLD = 0.18
    settings.HYBRID_BM25_WEIGHT = 0.35
    settings.HYBRID_VECTOR_WEIGHT = 0.65
    settings.HYBRID_MIN_VECTOR_SCORE = 0.12
    settings.HYBRID_MIN_BM25_SCORE = 0.04
    settings.HYBRID_MIN_LABEL_SCORE = 0.55

    class _NoNetworkBedrock:
        def invoke_model(self, **_kwargs):
            raise RuntimeError("No network in tests")

    settings.bedrock_runtime = _NoNetworkBedrock()
    sys.modules["settings"] = settings


_install_settings_stub()

from retrieval import (  # noqa: E402
    build_symptom_query,
    clean_ir_query_component,
    has_ir_eligible_symptom_span,
    is_generic_symptom_hint,
    should_skip_active_symptom_ir,
)


# --- is_generic_symptom_hint ---

def test_generic_hints_detected():
    assert is_generic_symptom_hint("불편") is True
    assert is_generic_symptom_hint("불편함") is True
    assert is_generic_symptom_hint("증상") is True
    assert is_generic_symptom_hint("통증") is True
    assert is_generic_symptom_hint("몸살 느낌") is True
    assert is_generic_symptom_hint("") is True


def test_specific_hints_not_generic():
    assert is_generic_symptom_hint("기침") is False
    assert is_generic_symptom_hint("두통") is False
    assert is_generic_symptom_hint("코막힘") is False
    assert is_generic_symptom_hint("목 칼칼함") is False


# --- clean_ir_query_component ---

def test_clean_removes_speaker_markers():
    # "환자" 단독 단어가 \b로 매칭됨 - 한국어에서는 조사가 붙으면 다를 수 있음
    # "환자가" 같은 조사가 붙은 표현도 패턴에 해당
    result = clean_ir_query_component("[환자] 기침이 난다고 합니다")
    assert "[환자]" not in result
    assert "기침" in result


def test_clean_removes_agenda_expressions():
    result = clean_ir_query_component("의사에게 궁금한 것")
    assert "의사에게" not in result
    assert "궁금" not in result


def test_clean_empty():
    assert clean_ir_query_component("") == ""
    assert clean_ir_query_component(None) == ""


# --- build_symptom_query ---

def test_build_query_uses_normalized_and_hint():
    query = build_symptom_query("목이 칼칼해요", "목 자극감", "목 통증")
    assert "목" in query
    assert "자극감" in query or "통증" in query


def test_build_query_falls_back_to_normalized_only_for_generic_hint():
    query = build_symptom_query("기침이 나요", "기침이 남", "불편함")
    # "불편함"은 generic이므로 제외
    assert "기침" in query
    assert "불편" not in query


def test_build_query_falls_back_to_source_quote():
    query = build_symptom_query("코가 막혀요", "", "")
    assert "코" in query
    assert "막혀" in query or "막" in query


def test_build_query_all_empty():
    query = build_symptom_query("", "", "")
    assert query == ""


# --- has_ir_eligible_symptom_span ---

def test_eligible_active_symptom():
    span = {"type": "symptom", "slot_ref": "cough", "status": "있음"}
    assert has_ir_eligible_symptom_span(span) is True


def test_eligible_new_symptom():
    span = {"type": "new", "slot_ref": "other", "status": "있음"}
    assert has_ir_eligible_symptom_span(span) is True


def test_non_eligible_medication():
    span = {"type": "medication", "slot_ref": "other", "status": "있음"}
    assert has_ir_eligible_symptom_span(span) is False


def test_non_eligible_absent_symptom():
    span = {"type": "symptom_absent", "slot_ref": "cough", "status": "없음"}
    assert has_ir_eligible_symptom_span(span) is False


def test_non_eligible_improved():
    span = {"type": "progress_improved", "slot_ref": "cough", "status": "없음"}
    assert has_ir_eligible_symptom_span(span) is False


def test_non_dict_not_eligible():
    assert has_ir_eligible_symptom_span(None) is False
    assert has_ir_eligible_symptom_span("string") is False


# --- should_skip_active_symptom_ir ---

def test_skip_absent_symptom():
    span = {"type": "symptom_absent", "status": "없음"}
    assert should_skip_active_symptom_ir(span) is True


def test_skip_improved():
    span = {"type": "progress_improved", "status": "없음"}
    assert should_skip_active_symptom_ir(span) is True


def test_dont_skip_active():
    span = {"type": "symptom", "status": "있음"}
    assert should_skip_active_symptom_ir(span) is False
