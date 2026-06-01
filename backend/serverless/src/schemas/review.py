"""Pydantic schema for the final onepaper review LLM.

Nova Pro가 의사용 체크리스트를 만들더라도 출력 형식은 이 모델을 통과해야 합니다.
의학적 근거 검증은 onepager_review.py의 sanitize 단계에서 이어서 수행합니다.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from utils import clean_quote

BriefKey = Literal["symptoms", "context", "medication", "agenda", "safety"]


def clean_required_text(value):
    """필수 문자열을 한 줄로 정리하고 빈 문자열을 거부합니다."""
    text = clean_quote(value)
    if not text:
        raise ValueError("required text is empty")
    return text


class StrictModel(BaseModel):
    """LLM이 schema에 없는 필드를 추가하면 실패시키는 공통 base model입니다."""

    model_config = ConfigDict(extra="forbid")


class DoctorBriefSection(StrictModel):
    """원페이퍼 상단/요약 영역에 들어갈 의사용 문맥 섹션입니다."""

    key: BriefKey
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    items: list[dict[str, Any] | str]

    @field_validator("title", "summary", mode="before")
    @classmethod
    def validate_text(cls, value):
        return clean_required_text(value)


class DoctorBrief(StrictModel):
    """의사가 원페이퍼를 빠르게 읽기 위한 요약 block입니다."""

    headline: str = Field(min_length=1)
    sections: list[DoctorBriefSection]

    @field_validator("headline", mode="before")
    @classmethod
    def validate_headline(cls, value):
        return clean_required_text(value)


class OnepagerReviewOutput(StrictModel):
    """Nova Pro final-review 출력 schema입니다."""

    review_items: list[str]
    transfer_text: str = Field(min_length=1)
    doctor_brief: DoctorBrief
    issues: list[str]

    @field_validator("review_items", "issues", mode="before")
    @classmethod
    def validate_string_list(cls, value):
        if not isinstance(value, list):
            raise ValueError("must be a list")
        return [clean_quote(item) for item in value if clean_quote(item)]

    @field_validator("transfer_text", mode="before")
    @classmethod
    def validate_transfer_text(cls, value):
        return clean_required_text(value)


def validate_review_payload(obj):
    """LLM review JSON을 Pydantic으로 검증하고 dict/errors를 반환합니다."""
    try:
        model = OnepagerReviewOutput.model_validate(obj)
        return model.model_dump(), []
    except ValidationError as exc:
        return None, format_validation_errors(exc)


def format_validation_errors(exc):
    """retry prompt에 넣을 수 있는 짧은 오류 배열로 변환합니다."""
    return [
        {
            "field": ".".join(str(part) for part in err.get("loc", [])),
            "type": err.get("type"),
            "message": err.get("msg"),
        }
        for err in exc.errors()
    ]
