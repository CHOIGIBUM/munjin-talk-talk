"""Scoring helpers for symptom retrieval.

BM25, cosine similarity, 표준 증상명 직접 유사도처럼 수학/검색 점수 계산만
담당합니다. retrieval.py는 이 점수를 어떻게 조합해 최종 증상을 채택할지에만
집중합니다.
"""

import math
import re

from utils import compact_ir, normalize_text


def tokenize_ir(text):
    """한국어 짧은 증상 표현에 맞게 단어 token과 2~3글자 n-gram을 함께 만듭니다."""
    text = normalize_text(text).lower()
    compacted = compact_ir(text.lower())
    tokens = re.findall(r"[가-힣a-z0-9]+", text)
    for n in (2, 3):
        if len(compacted) >= n:
            tokens.extend(compacted[i:i + n] for i in range(len(compacted) - n + 1))
    return [token for token in tokens if token]


class BM25Index:
    """작은 증상 문서 집합용 BM25 구현입니다."""

    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize_ir(((doc["display_name"] + " ") * 4) + doc.get("bm25_text", "")) for doc in docs]
        self.doc_lens = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lens) / max(1, len(self.doc_lens))
        self.df = {}
        self.tf = []
        for tokens in self.doc_tokens:
            counts = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            self.tf.append(counts)
            for token in counts:
                self.df[token] = self.df.get(token, 0) + 1
        self.N = len(docs)

    def idf(self, term):
        """문서 수가 작아도 0이 되지 않는 BM25 IDF를 계산합니다."""
        df = self.df.get(term, 0)
        return math.log(1 + (self.N - df + 0.5) / (df + 0.5))

    def scores(self, query):
        """query와 각 문서 사이의 BM25 lexical score 배열을 반환합니다."""
        q_terms = tokenize_ir(query)
        if not q_terms:
            return [0.0] * self.N
        scores = []
        for idx, counts in enumerate(self.tf):
            dl = self.doc_lens[idx] or 1
            score = 0.0
            for term in q_terms:
                freq = counts.get(term, 0)
                if freq <= 0:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1e-9))
                score += self.idf(term) * (freq * (self.k1 + 1)) / denom
            scores.append(float(score))
        return scores


def minmax_norm(values):
    """점수 배열을 0~1 범위로 정규화합니다."""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.0 for _ in values]
    return [(value - lo) / (hi - lo) for value in values]


def jaccard_char_ngram(a, b, n=2):
    """짧은 한글 증상명 비교용 문자 n-gram Jaccard 점수입니다."""
    a = compact_ir(a)
    b = compact_ir(b)
    if not a or not b:
        return 0.0
    aa = {a[i:i + n] for i in range(max(1, len(a) - n + 1))} if len(a) >= n else {a}
    bb = {b[i:i + n] for i in range(max(1, len(b) - n + 1))} if len(b) >= n else {b}
    return len(aa & bb) / max(1, len(aa | bb))


def cosine(a, b):
    """Titan embedding vector 간 cosine similarity를 계산합니다."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def direct_label_score(query, label):
    """LLM span과 표준 증상명이 직접 겹치는 정도를 계산합니다."""
    q = normalize_text(query)
    s = normalize_text(label)
    qc = compact_ir(q)
    sc = compact_ir(s)
    if not qc or not sc:
        return 0.0
    if qc == sc:
        return 1.0
    if len(sc) == 1:
        return 0.72 if any(token.startswith(s) for token in q.split()) else 0.0
    contains = 0.78 if sc in qc and len(sc) >= 2 else 0.0
    reverse_contains = 0.65 if qc in sc and len(qc) >= 2 else 0.0
    return max(contains, reverse_contains, jaccard_char_ngram(q, s, 2) * 0.75)
