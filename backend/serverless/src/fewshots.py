"""Domain-managed few-shot examples for LLM prompts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from domain_config import DOMAIN_DATA_DIR, get_domain_pack, selected_domain_pack_id
from utils import load_json_file


FEWSHOT_DIR = DOMAIN_DATA_DIR / "fewshots"
DEFAULT_LIMITS = {
    "extraction": 3,
    "standardization": 2,
    "semantic_unit": 3,
    "span_tagging": 3,
    "symptom_hint": 5,
    "onepager_review": 2,
}


def _safe_id(value: str, fallback: str = "respiratory") -> str:
    text = str(value or fallback).strip()
    if not text or "/" in text or "\\" in text or ".." in text:
        raise RuntimeError(f"Invalid few-shot id: {value}")
    return text


def _safe_stage(stage: str) -> str:
    text = str(stage or "").strip()
    if not text or "/" in text or "\\" in text or ".." in text:
        raise RuntimeError(f"Invalid few-shot stage: {stage}")
    return text


def _resolve_configured_path(configured_path: str) -> Path:
    text = str(configured_path or "").strip()
    if not text or "\\" in text or ".." in text:
        raise RuntimeError(f"Invalid few-shot path: {configured_path}")
    path = Path(text)
    if path.is_absolute():
        raise RuntimeError(f"Few-shot path must be relative to data/: {configured_path}")
    return DOMAIN_DATA_DIR / path


def _candidate_paths(stage: str, pack_id: str) -> list[Path]:
    pack = get_domain_pack(pack_id)
    paths: list[Path] = []
    configured = (pack.get("fewshot_sets") or {}).get(stage)
    if configured:
        paths.append(_resolve_configured_path(configured))
    fewshot_id = _safe_id(str(pack.get("fewshot_id") or pack_id), pack_id)
    paths.append(FEWSHOT_DIR / fewshot_id / f"{stage}.json")
    if stage == "extraction":
        paths.append(DOMAIN_DATA_DIR / "domain_packs" / f"{fewshot_id}_fewshot.txt")
    return paths


@lru_cache(maxsize=None)
def load_fewshot_payload(stage: str, pack_id: str | None = None) -> dict[str, Any]:
    """Load the first configured few-shot payload for a stage.

    JSON files are preferred.  The legacy ``*_fewshot.txt`` file is kept as a
    read-only fallback for older packs, but new packs should use JSON.
    """
    safe_stage = _safe_stage(stage)
    safe_pack_id = _safe_id(pack_id or selected_domain_pack_id())
    for path in _candidate_paths(safe_stage, safe_pack_id):
        if not path.exists():
            continue
        if path.suffix.lower() == ".txt":
            text = path.read_text(encoding="utf-8").strip()
            return {"stage": safe_stage, "raw_text": text, "examples": []}
        payload = load_json_file(path)
        if isinstance(payload, list):
            return {"stage": safe_stage, "examples": payload}
        if isinstance(payload, dict):
            examples = payload.get("examples")
            if not isinstance(examples, list):
                raise RuntimeError(f"Few-shot file missing examples list: {path}")
            return payload
        raise RuntimeError(f"Invalid few-shot file: {path}")
    return {"stage": safe_stage, "examples": []}


def load_fewshot_examples(stage: str, pack_id: str | None = None) -> list[dict[str, Any]]:
    payload = load_fewshot_payload(stage, pack_id)
    examples = payload.get("examples") or []
    return [item for item in examples if isinstance(item, dict)]


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _append_field(lines: list[str], label: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    formatted = _format_value(value)
    if "\n" in formatted:
        lines.extend([f"{label}:", formatted])
    else:
        lines.append(f"{label}: {formatted}")


def _render_example(index: int, example: dict[str, Any]) -> list[str]:
    title = str(example.get("title") or "").strip()
    lines = [f"Example {index}" + (f" - {title}" if title else "")]
    fields = [
        ("Visit type", "visit_type"),
        ("Question id", "question_id"),
        ("Question type", "question_type"),
        ("Question asked", "question"),
        ("Patient answer", "patient_answer"),
        ("Original", "original"),
        ("Standardized", "standardized"),
        ("Input", "input"),
        ("Meaning units JSON", "meaning_units"),
        ("Tagged spans JSON", "tagged_spans"),
        ("Expected JSON", "expected_json"),
        ("Expected output", "expected_output"),
    ]
    for label, key in fields:
        _append_field(lines, label, example.get(key))
    return lines


def select_fewshot_examples(
    stage: str,
    pack_id: str | None = None,
    limit: int | None = None,
    *,
    visit_type: str = "",
    question_id: str = "",
    question_type: str = "",
) -> list[dict[str, Any]]:
    """Select the most relevant examples for the current prompt context."""
    examples = load_fewshot_examples(stage, pack_id)
    max_examples = DEFAULT_LIMITS.get(_safe_stage(stage), 3) if limit is None else max(0, int(limit))
    if not examples or max_examples <= 0:
        return []

    visit_type = str(visit_type or "").strip()
    question_id = str(question_id or "").strip()
    question_type = str(question_type or "").strip()
    if not any([visit_type, question_id, question_type]):
        return examples[:max_examples]

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, example in enumerate(examples):
        score = 0
        if question_type and str(example.get("question_type") or "") == question_type:
            score += 4
        if question_id and str(example.get("question_id") or "") == question_id:
            score += 3
        if visit_type and str(example.get("visit_type") or "") == visit_type:
            score += 2
        scored.append((score, idx, example))

    selected = [example for score, _idx, example in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0]
    if len(selected) < max_examples:
        selected_ids = {id(example) for example in selected}
        selected.extend(example for _score, _idx, example in sorted(scored, key=lambda item: item[1]) if id(example) not in selected_ids)
    return selected[:max_examples]


def render_fewshot_block(
    stage: str,
    pack_id: str | None = None,
    limit: int | None = None,
    *,
    visit_type: str = "",
    question_id: str = "",
    question_type: str = "",
) -> str:
    """Render a compact prompt block for a prompt stage."""
    payload = load_fewshot_payload(stage, pack_id)
    raw_text = str(payload.get("raw_text") or "").strip()
    if raw_text:
        return raw_text

    selected = select_fewshot_examples(
        stage,
        pack_id,
        limit,
        visit_type=visit_type,
        question_id=question_id,
        question_type=question_type,
    )
    if not selected:
        return ""

    lines = [
        "Few-shot examples:",
        "Use these only as behavior examples. Do not copy facts into the current patient.",
    ]
    for idx, example in enumerate(selected, start=1):
        lines.append("")
        lines.extend(_render_example(idx, example))
    return "\n".join(lines)
