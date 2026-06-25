"""AWS Lambda HTTP entrypoint.

이 파일은 API Gateway에서 들어온 요청을 URL별 업무 함수로만 넘깁니다.
실제 세션 저장, STT, LLM, IR, 원페이퍼 생성 로직은 각 전용 모듈에
분리되어 있으므로, 새 API를 추가할 때는 이 파일에서 route만 연결합니다.
"""

import re
import json
import traceback
from urllib.parse import unquote_plus

from audio import generate_streaming_transcribe_url
from guide import get_guide, save_doctor_response
from onepager import get_onepager_payload, rerun_onepager_review
from orchestration import handle_internal_event, process_answer, process_answers, retry_answer_analysis
from question_sets import public_question_set
from security import is_auth_configured, issue_role_token, require_patient_session, require_role, role_for_event, verify_access_code
from sessions import create_session, delete_session, get_session, list_sessions, public_session, save_patient_consent, update_session
from utils import parse_body, response, set_request_origin


def handler(event, context):
    """Lambda가 처음 호출하는 함수. HTTP method/path를 꺼내 route()로 전달합니다."""
    if event.get("source") == "munjin.analysis":
        return handle_internal_event(event, context)

    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
    path = event.get("rawPath") or event.get("path") or "/"
    path = path.rstrip("/") or "/"
    event_headers = event.get("headers") or {}
    set_request_origin(event_headers.get("origin") or event_headers.get("Origin") or "")

    if method == "OPTIONS":
        return response(200, {"ok": True})

    try:
        return route(method, path, event)
    except Exception as exc:
        print(json.dumps({
            "level": "error",
            "error": "unhandled_exception",
            "path": path,
            "method": method,
            "exception_type": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
            "aws_request_id": getattr(context, "aws_request_id", ""),
        }, ensure_ascii=False))
        return response(
            500,
            {
                "error": "internal_error",
                "message": "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            },
        )


def route(method, path, event):
    """문진톡톡 MVP의 공개 API 라우팅 테이블입니다."""
    body = parse_body(event)

    if method == "POST" and path == "/auth/login":
        role = str(body.get("role") or "").strip()
        access_code = str(body.get("access_code") or body.get("accessCode") or "").strip()
        if not is_auth_configured(role):
            return response(
                503,
                {
                    "error": "auth_not_configured",
                    "message": "접근 코드 설정이 서버에 준비되지 않았습니다.",
                },
            )
        if not verify_access_code(role, access_code):
            return response(
                401,
                {
                    "error": "invalid_access_code",
                    "message": "접근 코드가 맞지 않습니다. 다시 확인해 주세요.",
                },
            )
        return response(200, issue_role_token(role))

    if method == "POST" and path == "/sessions":
        auth_error = require_role(event, "staff")
        if auth_error:
            return auth_error
        session = create_session(body)
        return response(200, public_session(session, include_patient_token=True))

    match = re.fullmatch(r"/sessions/([^/]+)", path)
    if method == "GET" and match:
        session = get_session(unquote_plus(match.group(1)))
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff", "doctor"))
        if auth_error:
            return auth_error
        include_token = role_for_event(event) == "staff"
        return response(200, public_session(session, include_artifacts=True, include_patient_token=include_token))

    if method == "DELETE" and match:
        auth_error = require_role(event, "staff")
        if auth_error:
            return auth_error
        session_id = unquote_plus(match.group(1))
        if not delete_session(session_id):
            return response(404, {"error": "session_not_found"})
        return response(200, {"deleted": True, "session_id": session_id})

    match = re.fullmatch(r"/sessions/([^/]+)/staff-help", path)
    if method == "POST" and match:
        session_id = unquote_plus(match.group(1))
        session = get_session(session_id)
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff",))
        if auth_error:
            return auth_error
        session = update_session(session_id, {"status": "staff_help"})
        return response(200, public_session(session))

    match = re.fullmatch(r"/sessions/([^/]+)/consent", path)
    if method == "POST" and match:
        session_id = unquote_plus(match.group(1))
        session = get_session(session_id)
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff",))
        if auth_error:
            return auth_error
        session = save_patient_consent(session_id, body)
        return response(200, public_session(session))

    if method == "POST" and path == "/transcribe-stream-url":
        session = get_session(body.get("session_id") or body.get("sessionId"))
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff",))
        if auth_error:
            return auth_error
        payload, err = generate_streaming_transcribe_url(body)
        return err or response(200, payload)

    if method == "POST" and path == "/process-answer":
        session = get_session(body.get("session_id") or body.get("sessionId"))
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff",))
        if auth_error:
            return auth_error
        payload, err = process_answer(body)
        return err or response(200, payload)

    if method == "POST" and path == "/process-answers":
        session = get_session(body.get("session_id") or body.get("sessionId"))
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff",))
        if auth_error:
            return auth_error
        payload, err = process_answers(body)
        return err or response(200, payload)

    match = re.fullmatch(r"/question-sets/([^/]+)", path)
    if method == "GET" and match:
        question_set = public_question_set(unquote_plus(match.group(1)))
        if not question_set:
            return response(404, {"error": "question_set_not_found"})
        return response(200, question_set)

    if method == "GET" and path == "/doctor/queue":
        auth_error = require_role(event, "staff", "doctor")
        if auth_error:
            return auth_error
        return response(200, {"sessions": list_sessions(include_patient_token=role_for_event(event) == "staff")})

    match = re.fullmatch(r"/onepager/([^/]+)", path)
    if method == "GET" and match:
        auth_error = require_role(event, "staff", "doctor")
        if auth_error:
            return auth_error
        session_id = unquote_plus(match.group(1))
        session = get_session(session_id)
        if not session:
            return response(404, {"error": "session_not_found"})
        return response(200, get_onepager_payload(session))

    match = re.fullmatch(r"/onepager/([^/]+)/review", path)
    if method == "POST" and match:
        auth_error = require_role(event, "doctor")
        if auth_error:
            return auth_error
        payload, err = rerun_onepager_review(unquote_plus(match.group(1)))
        return err or response(200, payload)

    match = re.fullmatch(r"/sessions/([^/]+)/analysis/retry", path)
    if method == "POST" and match:
        auth_error = require_role(event, "staff", "doctor")
        if auth_error:
            return auth_error
        payload, err = retry_answer_analysis(unquote_plus(match.group(1)))
        return err or response(200, payload)

    if method == "POST" and path == "/doctor-response":
        auth_error = require_role(event, "doctor")
        if auth_error:
            return auth_error
        payload, err = save_doctor_response(body)
        return err or response(200, payload)

    match = re.fullmatch(r"/guide/([^/]+)", path)
    if method == "GET" and match:
        session_id = unquote_plus(match.group(1))
        session = get_session(session_id)
        if not session:
            return response(404, {"error": "session_not_found"})
        auth_error = require_patient_session(event, session, body, allow_roles=("staff", "doctor"))
        if auth_error:
            return auth_error
        guide = get_guide(session_id)
        if not guide:
            return response(404, {"error": "session_not_found"})
        return response(200, guide)

    return response(404, {"error": "not_found", "method": method, "path": path})
