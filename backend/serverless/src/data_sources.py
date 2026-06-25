"""Domain-aware runtime data path resolution.

The production Lambda normally reads private Asan-derived IR files from
``src/data``.  For multi-domain deployments, the same filenames can live under
``src/data/ir_sources/{domain_id}`` and will be selected automatically from the
active domain pack.
"""

from __future__ import annotations

import os
from pathlib import Path

from domain_config import get_domain_pack, selected_domain_pack_id


DATA_DIR = Path(__file__).resolve().parent / "data"
IR_SOURCE_DIR = DATA_DIR / "ir_sources"


def _safe_id(value: str, fallback: str) -> str:
    text = str(value or fallback).strip()
    if not text or "/" in text or "\\" in text or ".." in text:
        raise RuntimeError(f"Invalid data source id: {value}")
    return text


def selected_ir_source_id(domain_pack_id: str | None = None) -> str:
    """Return the IR source id for the active domain pack.

    Domain packs may set ``ir_source_id`` when multiple packs share the same
    source dataset.  If absent, the domain pack id itself is used.
    """
    pack_id = _safe_id(domain_pack_id or selected_domain_pack_id(), "respiratory")
    pack = get_domain_pack(pack_id)
    return _safe_id(str(pack.get("ir_source_id") or pack_id), pack_id)


def domain_ir_source_dir(domain_pack_id: str | None = None) -> Path:
    """Directory containing domain-specific private IR source files."""
    return IR_SOURCE_DIR / selected_ir_source_id(domain_pack_id)


def resolve_ir_source_path(filename: str, env_var: str = "", domain_pack_id: str | None = None) -> Path:
    """Resolve an IR source file with explicit env, domain, then legacy fallback.

    Resolution order:
    1. Explicit environment variable path, when provided.
    2. ``data/ir_sources/{ir_source_id}/{filename}``, when the file exists.
    3. Legacy ``data/{filename}`` path for the current respiratory deployment.
    """
    if env_var:
        explicit = os.environ.get(env_var, "").strip()
        if explicit:
            return Path(explicit)
    domain_path = domain_ir_source_dir(domain_pack_id) / filename
    if domain_path.exists():
        return domain_path
    return DATA_DIR / filename


def embedding_cache_filename(model_id: str, dimensions: int) -> str:
    safe_model_id = str(model_id).replace(":", "_").replace("/", "_")
    return f"symptom_embeddings_{safe_model_id}_{int(dimensions)}.json"


def resolve_embedding_cache_path(model_id: str, dimensions: int, domain_pack_id: str | None = None) -> Path:
    """Resolve the packaged Titan embedding cache for the active IR source."""
    explicit = os.environ.get("EMBEDDING_CACHE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    filename = embedding_cache_filename(model_id, dimensions)
    domain_path = domain_ir_source_dir(domain_pack_id) / filename
    if domain_path.exists():
        return domain_path
    return DATA_DIR / filename
