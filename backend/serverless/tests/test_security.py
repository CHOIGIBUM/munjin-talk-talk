"""security.py 인증/접근제어 단위 테스트.

settings 의존을 stub으로 주입해 AWS 없이 토큰 발급/검증 로직을 검증합니다.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_security(staff_code="staff-secret", doctor_code="doctor-secret",
                      staff_hash="", doctor_hash="", signing="unit-test-signing-secret"):
    for name in ["settings", "security", "utils"]:
        sys.modules.pop(name, None)
    settings = types.ModuleType("settings")
    settings.AUTH_SIGNING_SECRET = signing
    settings.AUTH_TOKEN_TTL_MINUTES = 240
    settings.STAFF_ACCESS_CODE = staff_code
    settings.DOCTOR_ACCESS_CODE = doctor_code
    settings.STAFF_ACCESS_CODE_SHA256 = staff_hash
    settings.DOCTOR_ACCESS_CODE_SHA256 = doctor_hash
    sys.modules["settings"] = settings
    return importlib.import_module("security")


# --- verify_access_code ---

def test_correct_access_code_accepted():
    sec = _install_security()
    assert sec.verify_access_code("staff", "staff-secret") is True
    assert sec.verify_access_code("doctor", "doctor-secret") is True


def test_wrong_access_code_rejected():
    sec = _install_security()
    assert sec.verify_access_code("staff", "wrong") is False
    assert sec.verify_access_code("doctor", "") is False


def test_unknown_role_rejected():
    sec = _install_security()
    assert sec.verify_access_code("admin", "anything") is False


def test_sha256_hash_verification():
    import hashlib
    code = "my-secret-code"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    sec = _install_security(staff_code="", staff_hash=code_hash)
    assert sec.verify_access_code("staff", code) is True
    assert sec.verify_access_code("staff", "wrong") is False


# --- issue / verify role token ---

def test_issue_and_verify_role_token_roundtrip():
    sec = _install_security()
    token_data = sec.issue_role_token("doctor")
    assert token_data["token_type"] == "Bearer"
    assert token_data["role"] == "doctor"

    event = {"headers": {"authorization": f"Bearer {token_data['access_token']}"}}
    assert sec.role_for_event(event) == "doctor"


def test_tampered_token_rejected():
    sec = _install_security()
    token = sec.issue_role_token("staff")["access_token"]
    # 서명 부분을 변조
    payload_segment, _sig = token.rsplit(".", 1)
    tampered = f"{payload_segment}.AAAAtampered"
    event = {"headers": {"authorization": f"Bearer {tampered}"}}
    assert sec.role_for_event(event) is None


def test_token_signed_with_different_secret_rejected():
    sec1 = _install_security(signing="secret-one")
    token = sec1.issue_role_token("staff")["access_token"]
    # 다른 서명 키로 서버 재구성
    sec2 = _install_security(signing="secret-two")
    event = {"headers": {"authorization": f"Bearer {token}"}}
    assert sec2.role_for_event(event) is None


def test_no_token_returns_none():
    sec = _install_security()
    assert sec.role_for_event({"headers": {}}) is None
    assert sec.role_for_event({}) is None


# --- require_role ---

def test_require_role_passes_for_correct_role():
    sec = _install_security()
    token = sec.issue_role_token("staff")["access_token"]
    event = {"headers": {"authorization": f"Bearer {token}"}}
    # 통과 시 None
    assert sec.require_role(event, "staff") is None


def test_require_role_forbidden_for_wrong_role():
    sec = _install_security()
    token = sec.issue_role_token("staff")["access_token"]
    event = {"headers": {"authorization": f"Bearer {token}"}}
    result = sec.require_role(event, "doctor")  # staff 토큰으로 doctor 요구
    assert result is not None
    assert result["statusCode"] == 403


def test_require_role_not_configured_returns_503():
    sec = _install_security(staff_code="", doctor_code="", signing="")
    result = sec.require_role({"headers": {}}, "staff")
    assert result is not None
    assert result["statusCode"] == 503


# --- patient token ---

def test_patient_token_from_header():
    sec = _install_security()
    event = {"headers": {"x-munjin-patient-token": "tok123"}}
    assert sec.patient_token(event) == "tok123"


def test_patient_token_from_query():
    sec = _install_security()
    event = {"headers": {}, "rawQueryString": "pt=tokABC"}
    assert sec.patient_token(event) == "tokABC"


def test_require_patient_session_with_correct_token():
    sec = _install_security()
    session = {"patient_access": {"token": "secret-token"}}
    event = {"headers": {"x-munjin-patient-token": "secret-token"}}
    assert sec.require_patient_session(event, session, allow_roles=()) is None


def test_require_patient_session_with_wrong_token():
    sec = _install_security()
    session = {"patient_access": {"token": "secret-token"}}
    event = {"headers": {"x-munjin-patient-token": "wrong-token"}}
    result = sec.require_patient_session(event, session, allow_roles=())
    assert result is not None
    assert result["statusCode"] == 403


def test_require_patient_session_allows_internal_role():
    sec = _install_security()
    token = sec.issue_role_token("doctor")["access_token"]
    session = {"patient_access": {"token": "secret-token"}}
    event = {"headers": {"authorization": f"Bearer {token}"}}
    # doctor 역할은 환자 토큰 없이도 허용
    assert sec.require_patient_session(event, session, allow_roles=("doctor",)) is None
