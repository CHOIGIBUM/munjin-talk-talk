"""privacy.py의 redact/가명처리 함수 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from privacy import (
    age_band,
    consent_summary,
    is_birth_key,
    redact_payload,
    redact_text,
    safety_summary,
    sanitize_reception_patient,
)


# --- age_band ---

def test_age_band_normal():
    assert age_band(75) == "70대"
    assert age_band(65) == "60대"
    assert age_band(80) == "80대"
    assert age_band(5) == "0대"


def test_age_band_invalid():
    assert age_band(-1) == ""
    assert age_band(None) == ""
    assert age_band("abc") == ""


# --- redact_text ---

def test_redact_phone_number():
    text = "연락처는 010-1234-5678입니다."
    result = redact_text(text)
    assert "010-1234-5678" not in result
    assert "[연락처]" in result


def test_redact_email():
    text = "이메일은 patient@hospital.com입니다."
    result = redact_text(text)
    assert "patient@hospital.com" not in result
    assert "[이메일]" in result


def test_redact_rrn():
    text = "주민번호 900101-1234567"
    result = redact_text(text)
    assert "1234567" not in result
    assert "[주민번호]" in result


def test_redact_birth_date_in_context():
    text = "생년월일 1950-03-15"
    result = redact_text(text)
    assert "[생년월일]" in result


def test_redact_birth_date_standalone_only_when_flagged():
    text = "날짜는 1950-03-15입니다."
    # 생년월일 맥락이 아닌 경우 기본적으로 날짜를 마스킹하지 않음
    result = redact_text(text, redact_birth_date=False)
    assert "1950" in result  # 맥락이 없으므로 유지

    result2 = redact_text(text, redact_birth_date=True)
    assert "[생년월일]" in result2


# --- redact_payload ---

def test_redact_payload_recursive_dict():
    payload = {
        "patient": {
            "phone": "010-1111-2222",
            "email": "test@test.com",
        },
        "text": "연락처 010-3333-4444",
    }
    result = redact_payload(payload)
    assert "[연락처]" in result["patient"]["phone"]
    assert "[이메일]" in result["patient"]["email"]
    assert "[연락처]" in result["text"]


def test_redact_payload_list():
    payload = ["010-1234-5678", "일반 텍스트"]
    result = redact_payload(payload)
    assert "[연락처]" in result[0]
    assert result[1] == "일반 텍스트"


def test_redact_payload_preserves_non_string():
    payload = {"count": 42, "active": True}
    result = redact_payload(payload)
    assert result["count"] == 42
    assert result["active"] is True


# --- is_birth_key ---

def test_is_birth_key():
    assert is_birth_key("birth_date") is True
    assert is_birth_key("birthDate") is True
    assert is_birth_key("생년월일") is True
    assert is_birth_key("dob") is True
    assert is_birth_key("name") is False
    assert is_birth_key(None) is False


# --- consent_summary ---

def test_consent_summary_extracts_key_fields():
    consent = {
        "accepted": True,
        "version": "v1",
        "method": "tablet_modal",
        "accepted_at": "2026-01-01T00:00:00",
        "rejected_at": None,
        "recorded_at": "2026-01-01T00:00:00",
        "privacy_items": ["항목1"],  # 이 필드는 요약에 포함되지 않아야 함
    }
    result = consent_summary(consent)
    assert result["accepted"] is True
    assert result["version"] == "v1"
    assert "privacy_items" not in result


# --- safety_summary ---

def test_safety_summary_none():
    assert safety_summary(None) is None


def test_safety_summary_extracts_fields():
    flag = {
        "type": "hemoptysis",
        "category": "hemoptysis",
        "label": "객혈 의심",
        "severity": "high",
        "matched_pattern": "피가 섞여",
        "message": "위험 표현 감지",
    }
    result = safety_summary(flag)
    assert result["type"] == "hemoptysis"
    assert result["severity"] == "high"
    assert "matched_pattern" not in result  # 요약에는 불포함
    assert "message" not in result


# --- sanitize_reception_patient ---

def test_sanitize_reception_patient_removes_pii():
    patient = {
        "full_name": "홍길동",
        "birth_date": "1950-01-01",
        "gender": "남",
        "receipt_id": "R-0001",
        "department": "내과",
        "doctor": "김의사",
        "phone": "010-1234-5678",
    }
    result = sanitize_reception_patient(patient)

    # 실명은 제거, 마스킹 이름만 남음
    assert result["name"] == "홍*동"
    assert "full_name" not in result
    assert "birth_date" not in result
    assert "phone" not in result
    assert result["gender"] == "남"
    assert result["department"] == "내과"
    assert result["age_band"]  # 나이대가 계산되어야 함
