"""API 접근 제어와 세션 토큰 검증을 담당하는 보안 헬퍼.

MVP라도 의료 문진 데이터는 URL만 알면 누구나 조회되는 구조가 되면 안 됩니다.
이 모듈은 세 가지 접근 주체를 구분합니다.

- staff: 접수 직원. 세션 생성, 태블릿 대기열, 수기 입력에 필요합니다.
- doctor: 의료진. 원페이퍼 조회, AI 재검토, 환자 안내문 작성에 필요합니다.
- patient: 특정 문진 세션의 환자. 세션별 난수 토큰으로 자기 세션만 접근합니다.

토큰은 Lambda 환경 변수 또는 세션 데이터에 저장된 값을 상수 시간 비교로 검증합니다.
"""

from __future__ import annotations

import hmac
from typing import Any
from urllib.parse import parse_qs

from settings import DOCTOR_ACCESS_TOKEN, STAFF_ACCESS_TOKEN
from utils import response


ACCESS_HEADER = "x-munjin-access-token"
PATIENT_HEADER = "x-munjin-patient-token"


def headers(event: dict[str, Any]) -> dict[str, str]:
    """API Gateway header를 소문자 key dict로 정규화합니다."""
    return {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items() if v is not None}


def query_params(event: dict[str, Any]) -> dict[str, str]:
    """REST/HTTP API 양쪽 이벤트 형식에서 query string을 꺼냅니다."""
    direct = event.get("queryStringParameters") or {}
    if direct:
        return {str(k): str(v) for k, v in direct.items() if v is not None}
    raw = event.get("rawQueryString") or ""
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _bearer_value(value: str) -> str:
    value = str(value or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def access_token(event: dict[str, Any]) -> str:
    """직원/의료진 접근 토큰을 header에서 꺼냅니다."""
    hs = headers(event)
    return _bearer_value(hs.get(ACCESS_HEADER) or hs.get("authorization") or "")


def patient_token(event: dict[str, Any], body: dict[str, Any] | None = None) -> str:
    """환자 세션 토큰을 header, query string, body 순서로 확인합니다."""
    hs = headers(event)
    qs = query_params(event)
    body = body or {}
    return str(
        hs.get(PATIENT_HEADER)
        or qs.get("pt")
        or qs.get("patient_token")
        or body.get("patient_token")
        or body.get("patientToken")
        or ""
    ).strip()


def _same(left: str, right: str) -> bool:
    """토큰 비교 시 타이밍 차이를 줄이기 위해 compare_digest를 사용합니다."""
    if not left or not right:
        return False
    return hmac.compare_digest(str(left), str(right))


def role_for_event(event: dict[str, Any]) -> str | None:
    """요청 header의 접근 토큰이 어떤 역할인지 판별합니다."""
    token = access_token(event)
    if _same(token, STAFF_ACCESS_TOKEN):
        return "staff"
    if _same(token, DOCTOR_ACCESS_TOKEN):
        return "doctor"
    return None


def _missing_role_token(role: str) -> bool:
    if role == "staff":
        return not STAFF_ACCESS_TOKEN
    if role == "doctor":
        return not DOCTOR_ACCESS_TOKEN
    return False


def forbidden(message: str = "접근 권한이 없습니다."):
    return response(403, {"error": "forbidden", "message": message})


def auth_not_configured(role: str):
    return response(
        503,
        {
            "error": "access_token_not_configured",
            "message": f"{role} 접근 토큰이 서버 환경 변수에 설정되지 않았습니다.",
        },
    )


def require_role(event: dict[str, Any], *roles: str):
    """요청이 허용된 역할 중 하나인지 확인합니다. 통과 시 None을 반환합니다."""
    actual = role_for_event(event)
    if actual in roles:
        return None
    if all(_missing_role_token(role) for role in roles):
        return auth_not_configured("/".join(roles))
    return forbidden()


def session_patient_secret(session: dict[str, Any] | None) -> str:
    """DynamoDB 세션에 저장된 환자 전용 토큰을 반환합니다."""
    if not session:
        return ""
    patient_access = session.get("patient_access") or {}
    return str(patient_access.get("token") or session.get("patient_token") or "").strip()


def require_patient_session(
    event: dict[str, Any],
    session: dict[str, Any],
    body: dict[str, Any] | None = None,
    allow_roles: tuple[str, ...] = ("staff", "doctor"),
):
    """환자 토큰 또는 허용된 내부 역할 토큰으로 특정 세션 접근을 검증합니다."""
    role = role_for_event(event)
    if role in allow_roles:
        return None

    expected = session_patient_secret(session)
    if not expected:
        return response(
            503,
            {
                "error": "patient_token_not_configured",
                "message": "세션에 환자 접근 토큰이 없습니다. 접수 화면에서 세션을 다시 생성해 주세요.",
            },
        )
    if _same(patient_token(event, body), expected):
        return None
    return forbidden("이 문진 세션에 접근할 수 없습니다.")
