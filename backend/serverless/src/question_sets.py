"""문진 질문 세트 로더.

질문 문구와 UI 메타데이터는 도메인팩이 아니라 question set으로 관리합니다.
도메인팩은 "어떤 증상/규칙을 허용하는가"를, 질문 세트는 "환자에게 무엇을
묻는가"를 담당합니다.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils import load_json_file, normalize_text


QUESTION_SET_DIR = Path(__file__).resolve().parent / "data" / "question_sets"
DEFAULT_QUESTION_SET = "default"
ALLOWED_QUESTION_TYPES = {
    "chief_complaint",
    "onset",
    "current_medications",
    "patient_questions",
    "progress",
    "adherence",
    "new_symptoms",
    "unresolved_questions",
}


def selected_question_set_id() -> str:
    """환경 변수에서 현재 사용할 질문 세트 id를 읽습니다."""
    return os.environ.get("QUESTION_SET", DEFAULT_QUESTION_SET) or DEFAULT_QUESTION_SET


def _question_set_path(question_set_id: str) -> Path | None:
    """question_set_id를 안전한 로컬 JSON 경로로 변환합니다."""
    safe_id = str(question_set_id or DEFAULT_QUESTION_SET).strip()
    if not safe_id or "/" in safe_id or "\\" in safe_id or ".." in safe_id:
        return None
    filename = safe_id if safe_id.endswith(".json") else f"{safe_id}.json"
    return QUESTION_SET_DIR / filename


@lru_cache(maxsize=None)
def get_question_set(question_set_id: str | None = None) -> dict[str, Any] | None:
    """질문 세트를 읽어 검증합니다. 존재하지 않는 id는 None으로 반환합니다."""
    set_id = question_set_id or selected_question_set_id()
    path = _question_set_path(set_id)
    if not path or not path.exists():
        return None
    question_set = load_json_file(path)
    validate_question_set(question_set, path)
    return question_set


def validate_question_set(question_set: dict[str, Any], path: Path | None = None) -> None:
    """질문 세트가 프론트/백엔드가 기대하는 고정 구조인지 확인합니다."""
    if not isinstance(question_set, dict):
        raise RuntimeError(f"Invalid question set: {path or '<memory>'}")
    visits = question_set.get("visits")
    if not isinstance(visits, dict):
        raise RuntimeError(f"Question set missing visits: {path or '<memory>'}")
    for visit_type in ("initial", "followup"):
        questions = visits.get(visit_type)
        if not isinstance(questions, list) or not questions:
            raise RuntimeError(f"Question set missing visit questions: {visit_type}")
        seen_ids: set[str] = set()
        for question in questions:
            if not isinstance(question, dict):
                raise RuntimeError(f"Invalid question row in {visit_type}")
            qid = str(question.get("id") or "").strip()
            qtype = str(question.get("question_type") or "").strip()
            title = str(question.get("title") or "").strip()
            if not qid or qid in seen_ids:
                raise RuntimeError(f"Duplicate or empty question id in {visit_type}: {qid}")
            if qtype not in ALLOWED_QUESTION_TYPES:
                raise RuntimeError(f"Invalid question_type for {qid}: {qtype}")
            if not title:
                raise RuntimeError(f"Question title is required for {qid}")
            seen_ids.add(qid)


def public_question_set(question_set_id: str) -> dict[str, Any] | None:
    """API 응답용으로 공개해도 되는 질문 세트 필드만 반환합니다."""
    question_set = get_question_set(question_set_id)
    if not question_set:
        return None
    return {
        "id": str(question_set.get("id") or question_set_id),
        "visits": question_set.get("visits") or {},
    }


def prompt_question_text(visit_type: str, question_id: str, question_set_id: str | None = None) -> str:
    """LLM prompt에 넣을 서버 확정 질문 문구를 반환합니다."""
    question_set = get_question_set(question_set_id)
    if not question_set:
        return ""
    questions = (question_set.get("visits") or {}).get(str(visit_type or "")) or []
    for question in questions:
        if str(question.get("id") or "") != str(question_id or ""):
            continue
        prompt_text = question.get("prompt_text")
        if prompt_text:
            return normalize_text(prompt_text)
        return normalize_text(question.get("title") or "")
    return ""
