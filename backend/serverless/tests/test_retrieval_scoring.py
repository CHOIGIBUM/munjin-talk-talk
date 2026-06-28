"""retrieval_scoring.py 핵심 함수 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from retrieval_scoring import (
    BM25Index,
    cosine,
    direct_label_score,
    jaccard_char_ngram,
    minmax_norm,
    tokenize_ir,
)


# --- tokenize_ir ---

def test_tokenize_ir_produces_word_and_ngram_tokens():
    tokens = tokenize_ir("기침이 나요")
    assert "기침이" in tokens
    assert "나요" in tokens
    # 2-gram/3-gram도 포함
    assert any(len(t) == 2 for t in tokens)
    assert any(len(t) == 3 for t in tokens)


def test_tokenize_ir_empty_input():
    assert tokenize_ir("") == []
    assert tokenize_ir("   ") == []


# --- minmax_norm ---

def test_minmax_norm_normalizes_to_zero_one():
    result = minmax_norm([1.0, 2.0, 3.0, 4.0, 5.0])
    assert result[0] == 0.0
    assert result[-1] == 1.0
    assert abs(result[2] - 0.5) < 1e-9


def test_minmax_norm_all_same_returns_zeros():
    result = minmax_norm([3.0, 3.0, 3.0])
    assert all(v == 0.0 for v in result)


def test_minmax_norm_empty():
    assert minmax_norm([]) == []


# --- cosine ---

def test_cosine_identical_vectors():
    vec = [1.0, 2.0, 3.0]
    assert abs(cosine(vec, vec) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine(a, b)) < 1e-9


def test_cosine_empty_or_mismatched():
    assert cosine([], []) == 0.0
    assert cosine([1.0], [1.0, 2.0]) == 0.0
    assert cosine(None, None) == 0.0


# --- direct_label_score ---

def test_direct_label_exact_match():
    assert direct_label_score("기침", "기침") == 1.0


def test_direct_label_contains():
    score = direct_label_score("심한 기침과 가래", "기침")
    assert score > 0.5


def test_direct_label_no_match():
    score = direct_label_score("두통", "기침")
    assert score < 0.3


# --- jaccard_char_ngram ---

def test_jaccard_identical():
    assert jaccard_char_ngram("기침", "기침") == 1.0


def test_jaccard_empty():
    assert jaccard_char_ngram("", "기침") == 0.0
    assert jaccard_char_ngram("기침", "") == 0.0


def test_jaccard_partial_overlap():
    score = jaccard_char_ngram("기침", "기침이")
    assert 0.0 < score < 1.0


# --- BM25Index ---

def test_bm25_index_basic_scoring():
    docs = [
        {"display_name": "기침", "symptom_id": "cough", "bm25_text": "기침 콜록 가래"},
        {"display_name": "두통", "symptom_id": "headache", "bm25_text": "두통 머리 아픔"},
        {"display_name": "코막힘", "symptom_id": "nasal", "bm25_text": "코 막힘 비강"},
    ]
    bm25 = BM25Index(docs)
    scores = bm25.scores("기침이 나요")
    # 기침 관련 문서가 가장 높아야 합니다
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_bm25_index_empty_query():
    docs = [{"display_name": "기침", "symptom_id": "cough", "bm25_text": "기침"}]
    bm25 = BM25Index(docs)
    scores = bm25.scores("")
    assert all(s == 0.0 for s in scores)


def test_bm25_idf_positive():
    docs = [
        {"display_name": "기침", "symptom_id": "cough", "bm25_text": "기침"},
        {"display_name": "두통", "symptom_id": "headache", "bm25_text": "두통"},
    ]
    bm25 = BM25Index(docs)
    # IDF should be positive for terms that appear in fewer docs
    assert bm25.idf("기침") > 0
