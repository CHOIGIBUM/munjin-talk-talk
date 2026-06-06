"""Titan embedding 호출과 문서 embedding cache.

`retrieval.py`가 검색 로직에 집중할 수 있도록 Bedrock embedding 호출과
패키징된 embedding cache 검증을 이 파일에 모았습니다.
"""

import hashlib
import json

from settings import (
    EMBEDDING_CACHE_PATH,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_ID,
    HYBRID_PRECOMPUTE_DOC_EMBEDDINGS,
    USE_TITAN_EMBEDDING,
    bedrock_runtime,
)
from utils import load_json_file, normalize_text

_IR_DOC_EMBEDDINGS = None
_EMBED_TEXT_CACHE = {}


def docs_hash(docs):
    """문서 embedding cache가 현재 원천 JSON과 맞는지 확인하기 위한 hash입니다."""
    source = "\n".join(f"{doc['symptom_id']}|{doc['display_name']}|{doc['embedding_text']}" for doc in docs)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def load_packaged_doc_embeddings(docs):
    """배포 패키지에 포함된 문서 embedding cache를 읽습니다."""
    if not EMBEDDING_CACHE_PATH.exists():
        return None
    try:
        data = load_json_file(EMBEDDING_CACHE_PATH)
        if data.get("model_id") != EMBEDDING_MODEL_ID:
            return None
        if int(data.get("dimensions") or 0) != EMBEDDING_DIMENSIONS:
            return None
        if data.get("docs_hash") != docs_hash(docs):
            return None
        embeddings = data.get("embeddings")
        return embeddings if isinstance(embeddings, dict) else None
    except Exception:
        return None


def embed_text(text):
    """Titan embedding query 호출. 같은 Lambda instance 안에서는 text별로 캐시합니다."""
    text = normalize_text(text)
    if not text or not USE_TITAN_EMBEDDING:
        return None
    key = f"{EMBEDDING_MODEL_ID}|{EMBEDDING_DIMENSIONS}|{text}"
    if key in _EMBED_TEXT_CACHE:
        return _EMBED_TEXT_CACHE[key]
    body = {"inputText": text, "dimensions": EMBEDDING_DIMENSIONS, "normalize": True}
    resp = bedrock_runtime.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    result = json.loads(resp["body"].read())
    embedding = result.get("embedding")
    if isinstance(embedding, list):
        _EMBED_TEXT_CACHE[key] = embedding
        return embedding
    return None


def get_doc_embeddings(docs):
    """패키징된 문서 embedding을 우선 사용하고, 없을 때만 런타임 계산을 시도합니다."""
    global _IR_DOC_EMBEDDINGS
    if _IR_DOC_EMBEDDINGS is not None:
        return _IR_DOC_EMBEDDINGS
    packaged = load_packaged_doc_embeddings(docs)
    if packaged is not None:
        _IR_DOC_EMBEDDINGS = packaged
        return _IR_DOC_EMBEDDINGS
    if not HYBRID_PRECOMPUTE_DOC_EMBEDDINGS:
        _IR_DOC_EMBEDDINGS = {}
        return _IR_DOC_EMBEDDINGS
    embeddings = {}
    for doc in docs:
        emb = embed_text(doc.get("embedding_text", ""))
        if emb:
            embeddings[doc["symptom_id"]] = emb
    _IR_DOC_EMBEDDINGS = embeddings
    return _IR_DOC_EMBEDDINGS
