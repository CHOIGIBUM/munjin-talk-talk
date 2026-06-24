"""개인정보 최소화와 저장 전 가명처리 helper.

이 모듈은 의료 판단을 하지 않습니다. 저장소에 들어가기 전에 직접식별정보
형태를 줄이고, DynamoDB에는 화면 목록에 필요한 최소 정보만 남기기 위한
문자열/객체 정리만 담당합니다.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from utils import calculate_age, mask_name


PHONE_PATTERN = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RRN_PATTERN = re.compile(r"\d{6}[-\s]?[1-4]\d{6}")
BIRTH_DATE_PATTERN = re.compile(r"\b(?:19|20)\d{2}[-./년\s]?\d{1,2}[-./월\s]?\d{1,2}일?\b")
BIRTH_CONTEXT_PATTERN = re.compile(
    r"(생년월일|생일|출생일|태어난\s*날).{0,12}"
    r"((?:19|20)\d{2}[-./년\s]?\d{1,2}[-./월\s]?\d{1,2}일?)"
)
DATE_REDACTION_KEYS = {"birth_date", "birthDate", "birthday", "dob", "생년월일", "생일", "출생일"}


def age_band(age: Any) -> str:
    """나이를 정확한 숫자 대신 10년 단위 연령대로 변환합니다."""
    try:
        value = int(age)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    return f"{value // 10 * 10}대"


def sanitize_reception_patient(patient_input: dict[str, Any]) -> dict[str, Any]:
    """접수 입력값에서 DynamoDB에 저장 가능한 최소 환자 표시 정보를 만듭니다.

    실명, 생년월일, 연락처 원문은 반환하지 않습니다. 생년월일은 나이 계산에만
    사용하고 폐기하며, 화면에는 마스킹 이름과 연령대/나이만 남깁니다.
    """
    full_name = (
        patient_input.get("full_name")
        or patient_input.get("fullName")
        or patient_input.get("name")
        or ""
    )
    birth_date = patient_input.get("birth_date") or patient_input.get("birthDate") or ""
    age = patient_input.get("age") or calculate_age(birth_date)
    receipt_id = patient_input.get("receipt_id") or patient_input.get("receiptId") or ""

    return {
        "name": mask_name(full_name),
        "name_mask_version": "v2",
        "age": age,
        "age_band": age_band(age),
        "gender": patient_input.get("gender") or "-",
        "receipt_id": receipt_id,
        "department": patient_input.get("department") or "이비인후과",
        "doctor": patient_input.get("doctor") or "이민우",
        "honorific": "어르신",
    }


def redact_text(text: Any, *, redact_birth_date: bool = False) -> str:
    """저장용 텍스트에서 대표적인 직접식별정보 패턴을 제거합니다.

    한국어 의료 발화 전체를 완벽히 익명화하는 기능은 아닙니다. 이 함수는
    저장 전 1차 안전망이며, S3에 저장된 artifact는 Macie 같은 사후 탐지로
    한 번 더 확인하는 구조를 전제로 합니다.
    """
    value = str(text or "")
    value = PHONE_PATTERN.sub("[연락처]", value)
    value = EMAIL_PATTERN.sub("[이메일]", value)
    value = RRN_PATTERN.sub("[주민번호]", value)
    if redact_birth_date:
        value = BIRTH_DATE_PATTERN.sub("[생년월일]", value)
    else:
        value = BIRTH_CONTEXT_PATTERN.sub(lambda m: m.group(0).replace(m.group(2), "[생년월일]"), value)
    return value


def redact_payload(payload: Any, key_context: str | None = None) -> Any:
    """dict/list/string payload를 재귀적으로 가명처리합니다.

    운영 시각(`recorded_at`, `stored_at`)이나 schema version에 들어간 날짜까지
    생년월일로 오탐하지 않도록, 날짜형 마스킹은 birth 관련 key나 명시적 문맥에서만
    수행합니다.
    """
    if isinstance(payload, str):
        return redact_text(payload, redact_birth_date=is_birth_key(key_context))
    if isinstance(payload, list):
        return [redact_payload(item, key_context) for item in payload]
    if isinstance(payload, dict):
        return {key: redact_payload(value, str(key)) for key, value in payload.items()}
    return deepcopy(payload)


def is_birth_key(key: str | None) -> bool:
    """필드명만으로 생년월일임이 명확할 때 날짜 전체를 마스킹합니다."""
    if not key:
        return False
    normalized = str(key).strip()
    return normalized in DATE_REDACTION_KEYS or any(token in normalized.lower() for token in ("birth", "dob"))


def consent_summary(consent: dict[str, Any]) -> dict[str, Any]:
    """DynamoDB에 남길 동의 이력 요약만 추립니다."""
    return {
        "accepted": bool(consent.get("accepted")),
        "version": consent.get("version"),
        "method": consent.get("method"),
        "accepted_at": consent.get("accepted_at"),
        "rejected_at": consent.get("rejected_at"),
        "recorded_at": consent.get("recorded_at"),
    }


def safety_summary(flag: dict[str, Any] | None) -> dict[str, Any] | None:
    """DynamoDB 대기열에 필요한 안전 플래그 요약만 남깁니다."""
    if not flag:
        return None
    return {
        "type": flag.get("type"),
        "category": flag.get("category"),
        "label": flag.get("label"),
        "severity": flag.get("severity"),
    }
