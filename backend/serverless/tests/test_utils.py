"""utils.py 공통 유틸리티 함수 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils import (
    calculate_age,
    clean_quote,
    compact_ir,
    ddb_value,
    find_keyword_quote,
    json_default,
    mask_name,
    normalize_text,
    normalize_visit_type,
    parse_body,
    sentence_directly_mentions_symptom,
    split_sentences_ir,
    trim_snippet,
    unique,
    visit_label,
)
from decimal import Decimal
import json


# --- normalize_text ---

def test_normalize_text_collapses_whitespace():
    assert normalize_text("  기침이   나요  ") == "기침이 나요"


def test_normalize_text_removes_zero_width():
    assert normalize_text("기침\u200b나요") == "기침 나요"


def test_normalize_text_none():
    assert normalize_text(None) == ""


# --- compact_ir ---

def test_compact_ir_removes_non_alphanum():
    assert compact_ir("기침이 나요!") == "기침이나요"
    assert compact_ir("목 통증.") == "목통증"


# --- mask_name ---

def test_mask_name_various_lengths():
    assert mask_name("김") == "*"
    assert mask_name("김윤") == "김*"
    assert mask_name("홍길동") == "홍*동"
    assert mask_name("남궁민수") == "남**수"


def test_mask_name_empty():
    assert mask_name("") == "환자"
    assert mask_name(None) == "환자"


# --- calculate_age ---

def test_calculate_age_valid():
    # 나이는 변하므로 최소한 양수인지만 확인
    age = calculate_age("1950-01-01")
    assert isinstance(age, int)
    assert age > 70


def test_calculate_age_invalid():
    assert calculate_age("") == ""
    assert calculate_age(None) == ""
    assert calculate_age("invalid") == ""


# --- normalize_visit_type ---

def test_normalize_visit_type():
    assert normalize_visit_type("followup") == "followup"
    assert normalize_visit_type("재진") == "followup"
    assert normalize_visit_type("initial") == "initial"
    assert normalize_visit_type("초진") == "initial"
    assert normalize_visit_type(None) == "initial"


def test_visit_label():
    assert visit_label("followup") == "재진"
    assert visit_label("initial") == "초진"


# --- ddb_value ---

def test_ddb_value_converts_float():
    assert ddb_value(3.14) == Decimal("3.14")


def test_ddb_value_recursive():
    result = ddb_value({"a": 1.5, "b": [2.5, 3]})
    assert result["a"] == Decimal("1.5")
    assert result["b"][0] == Decimal("2.5")
    assert result["b"][1] == 3


# --- json_default ---

def test_json_default_decimal_int():
    assert json_default(Decimal("42")) == 42


def test_json_default_decimal_float():
    assert json_default(Decimal("3.14")) == 3.14


# --- parse_body ---

def test_parse_body_valid_json():
    event = {"body": '{"key": "value"}'}
    assert parse_body(event) == {"key": "value"}


def test_parse_body_invalid_json():
    event = {"body": "not json"}
    assert parse_body(event) == {}


def test_parse_body_none():
    assert parse_body({}) == {}


# --- split_sentences_ir ---

def test_split_sentences_ir():
    text = "기침이 심합니다. 목도 정말 아파요. 짧은."
    result = split_sentences_ir(text)
    assert "기침이 심합니다" in result
    assert "목도 정말 아파요" in result
    # 8글자 미만은 제외됨
    assert "짧은" not in result


# --- sentence_directly_mentions_symptom ---

def test_sentence_mentions_symptom_contains():
    assert sentence_directly_mentions_symptom("기침이 심하게 나와요", "기침") is True


def test_sentence_mentions_symptom_multi_word():
    assert sentence_directly_mentions_symptom("목이 아프고 열이 나요", "목 통증") is False
    assert sentence_directly_mentions_symptom("목 통증이 있어요", "목 통증") is True


def test_sentence_mentions_symptom_no_match():
    assert sentence_directly_mentions_symptom("배가 아파요", "기침") is False


# --- trim_snippet ---

def test_trim_snippet_short():
    assert trim_snippet("짧은 텍스트") == "짧은 텍스트"


def test_trim_snippet_long():
    long_text = "가" * 200
    result = trim_snippet(long_text, max_len=50)
    assert len(result) <= 50
    assert result.endswith("…")


# --- clean_quote ---

def test_clean_quote():
    assert clean_quote("  기침이 나요.  ") == "기침이 나요"
    assert clean_quote('"기침"') == "기침"


# --- unique ---

def test_unique_preserves_order():
    assert unique(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_unique_skips_empty():
    assert unique(["a", "", "b", None, "a"]) == ["a", "b"]


# --- find_keyword_quote ---

def test_find_keyword_quote_found():
    text = "어제부터 기침이 심하게 나요"
    result = find_keyword_quote(text, ["기침"])
    assert "기침" in result


def test_find_keyword_quote_not_found():
    text = "별다른 증상 없어요"
    result = find_keyword_quote(text, ["기침", "두통"])
    assert result == ""
