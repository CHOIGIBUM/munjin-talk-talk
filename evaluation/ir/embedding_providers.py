"""IR 평가용 embedding provider 모음.

운영 Lambda는 현재 Bedrock Titan embedding을 사용합니다. 이 파일은 운영 코드를
바꾸지 않고 평가 환경에서만 `sentence-transformers` 계열 모델을 갈아 끼워
동일한 query와 동일한 증상 문서로 검색 성능을 비교하기 위한 adapter입니다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from retrieval_embeddings import (
    docs_hash as backend_docs_hash,
    embed_text as titan_embed_text,
    get_doc_embeddings as titan_get_doc_embeddings,
)
from settings import EMBEDDING_MODEL_ID
from utils import normalize_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "evaluation" / "ir" / "cache" / "embeddings"


class BaseEmbeddingProvider:
    """평가 코드가 provider 종류를 모르게 호출하는 공통 인터페이스입니다."""

    provider_name = "base"

    def __init__(self, model_name: str):
        self.model_name = model_name

    @property
    def description(self) -> str:
        return f"{self.provider_name}:{self.model_name}"

    def embed_text(self, text: str) -> list[float] | None:
        raise NotImplementedError

    def get_doc_embeddings(self, docs: list[dict[str, Any]]) -> dict[str, list[float]]:
        raise NotImplementedError


class BedrockTitanEmbeddingProvider(BaseEmbeddingProvider):
    """기존 운영 방식과 같은 Bedrock Titan embedding provider입니다."""

    provider_name = "bedrock-titan"

    def __init__(self):
        super().__init__(EMBEDDING_MODEL_ID)

    def embed_text(self, text: str) -> list[float] | None:
        return titan_embed_text(text)

    def get_doc_embeddings(self, docs: list[dict[str, Any]]) -> dict[str, list[float]]:
        return titan_get_doc_embeddings(docs)


class SentenceTransformersEmbeddingProvider(BaseEmbeddingProvider):
    """로컬 sentence-transformers 모델을 이용하는 평가용 provider입니다."""

    provider_name = "sentence-transformers"

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        batch_size: int = 8,
        cache_dir: Path | None = None,
    ):
        super().__init__(model_name)
        self.device = resolve_device(device)
        self.batch_size = max(1, int(batch_size))
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._query_cache: dict[str, list[float]] = {}

    @property
    def description(self) -> str:
        return f"{self.provider_name}:{self.model_name}@{self.device}"

    def _load_model(self):
        """모델 로딩을 첫 embedding 호출 시점까지 미뤄 초기 실행 비용을 줄입니다."""
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "`sentence-transformers`가 설치되어 있지 않습니다. "
                "`pip install -r evaluation\\ir\\requirements.txt`를 먼저 실행하세요."
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def embed_text(self, text: str) -> list[float] | None:
        text = normalize_text(text)
        if not text:
            return None
        if text in self._query_cache:
            return self._query_cache[text]
        embedding = self._encode_texts([text])[0]
        self._query_cache[text] = embedding
        return embedding

    def get_doc_embeddings(self, docs: list[dict[str, Any]]) -> dict[str, list[float]]:
        cache_path = self._doc_cache_path(docs)
        cached = self._read_doc_cache(cache_path, docs)
        if cached is not None:
            return cached

        texts = [normalize_text(doc.get("embedding_text", "")) for doc in docs]
        encoded = self._encode_texts(texts)
        embeddings = {
            doc["symptom_id"]: vector
            for doc, vector in zip(docs, encoded)
            if vector
        }
        self._write_doc_cache(cache_path, docs, embeddings)
        return embeddings

    def _encode_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector.tolist()] for vector in vectors]

    def _doc_cache_path(self, docs: list[dict[str, Any]]) -> Path:
        key = safe_file_name(f"{self.provider_name}_{self.model_name}_{backend_docs_hash(docs)}")
        return self.cache_dir / f"{key}.json"

    def _read_doc_cache(self, path: Path, docs: list[dict[str, Any]]) -> dict[str, list[float]] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if data.get("provider") != self.provider_name:
            return None
        if data.get("model_name") != self.model_name:
            return None
        if data.get("docs_hash") != backend_docs_hash(docs):
            return None
        embeddings = data.get("embeddings")
        return embeddings if isinstance(embeddings, dict) else None

    def _write_doc_cache(self, path: Path, docs: list[dict[str, Any]], embeddings: dict[str, list[float]]) -> None:
        sample = next(iter(embeddings.values()), [])
        payload = {
            "provider": self.provider_name,
            "model_name": self.model_name,
            "device": self.device,
            "batch_size": self.batch_size,
            "docs_hash": backend_docs_hash(docs),
            "embedding_dim": len(sample),
            "embeddings": embeddings,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_embedding_provider(
    provider: str,
    model_name: str | None = None,
    device: str = "auto",
    batch_size: int = 8,
    cache_dir: Path | None = None,
) -> BaseEmbeddingProvider:
    """CLI 옵션을 실제 embedding provider 객체로 변환합니다."""
    if provider == "bedrock-titan":
        return BedrockTitanEmbeddingProvider()
    if provider == "sentence-transformers":
        if not model_name:
            raise ValueError("--embedding-provider sentence-transformers 사용 시 --embedding-model이 필요합니다.")
        return SentenceTransformersEmbeddingProvider(model_name, device=device, batch_size=batch_size, cache_dir=cache_dir)
    raise ValueError(f"지원하지 않는 embedding provider입니다: {provider}")


def resolve_device(device: str) -> str:
    """사용자가 auto를 지정하면 CUDA 가능 여부를 확인하고, 아니면 CPU로 내립니다."""
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def safe_file_name(value: str) -> str:
    """모델명에 들어가는 `/`, `:` 등을 캐시 파일명에 안전한 문자로 바꿉니다."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:180]
