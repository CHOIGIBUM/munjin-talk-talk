"""LLM JSON 호출 호환 계층.

실제 Bedrock 호출은 `langchain_prompting.call_bedrock_json_chain()`에서
LangChain Runnable chain으로 실행합니다. 이 파일은 기존 extraction/review/guide
모듈이 공통 인터페이스로 LLM을 부를 수 있게 유지하는 얇은 wrapper입니다.
"""

from __future__ import annotations

from typing import Any

from langchain_prompting import call_bedrock_json_chain, extract_first_json_object


def call_bedrock_json(prompt: str, model_id: str, max_tokens: int) -> tuple[dict[str, Any], str]:
    """기존 호출부 호환용 함수입니다. parsed JSON과 raw text만 반환합니다."""
    parsed, raw_text, _meta = call_bedrock_json_with_meta(prompt, model_id, max_tokens)
    return parsed, raw_text


def call_bedrock_json_with_meta(
    prompt: str,
    model_id: str,
    max_tokens: int,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """LangChain Runnable 기반 Bedrock 호출 결과와 meta를 함께 반환합니다."""
    result = call_bedrock_json_chain(prompt, model_id, max_tokens)
    return (
        result.get("parsed") if isinstance(result.get("parsed"), dict) else {},
        str(result.get("raw_text") or ""),
        result.get("meta") if isinstance(result.get("meta"), dict) else {},
    )
