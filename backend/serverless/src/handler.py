import re
from urllib.parse import unquote_plus

from common import (
    build_onepager,
    create_session,
    extract_question,
    generate_upload_url,
    get_guide,
    get_or_start_transcript,
    get_session,
    list_sessions,
    match_slots,
    parse_body,
    public_session,
    response,
    save_doctor_response,
    update_session,
    validate_and_save,
)


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
    path = event.get("rawPath") or event.get("path") or "/"
    path = path.rstrip("/") or "/"

    if method == "OPTIONS":
        return response(200, {"ok": True})

    try:
        return route(method, path, event)
    except Exception as exc:
        return response(500, {"error": "internal_error", "message": str(exc)})


def route(method, path, event):
    body = parse_body(event)
    query = event.get("queryStringParameters") or {}

    if method == "POST" and path == "/sessions":
        session = create_session(body)
        return response(200, public_session(session))

    match = re.fullmatch(r"/sessions/([^/]+)", path)
    if method == "GET" and match:
        session = get_session(unquote_plus(match.group(1)))
        if not session:
            return response(404, {"error": "session_not_found"})
        return response(200, public_session(session))

    match = re.fullmatch(r"/sessions/([^/]+)/staff-help", path)
    if method == "POST" and match:
        session_id = unquote_plus(match.group(1))
        if not get_session(session_id):
            return response(404, {"error": "session_not_found"})
        session = update_session(session_id, {"status": "staff_help"})
        return response(200, public_session(session))

    if method == "POST" and path == "/upload-url":
        payload, err = generate_upload_url(body)
        return err or response(200, payload)

    if method == "GET" and path == "/transcribe-result":
        return get_or_start_transcript(query.get("jobName") or query.get("job_name"))

    if method == "POST" and path == "/extract":
        return response(200, extract_question(body))

    if method == "POST" and path == "/match":
        return response(200, match_slots(body))

    if method == "POST" and path == "/validate":
        payload, err = validate_and_save(body)
        return err or response(200, payload)

    if method == "GET" and path == "/doctor/queue":
        return response(200, {"sessions": list_sessions()})

    match = re.fullmatch(r"/onepager/([^/]+)", path)
    if method == "GET" and match:
        session_id = unquote_plus(match.group(1))
        session = get_session(session_id)
        if not session:
            return response(404, {"error": "session_not_found"})
        onepager = build_onepager(session)
        update_session(session_id, {"onepager": onepager})
        return response(200, {
            "session": {
                "session_id": session_id,
                "case_id": session_id,
                "visit_type": session.get("visit_type", "initial"),
                "responses": session.get("responses", {}),
                "onepager": onepager,
            }
        })

    if method == "POST" and path == "/doctor-response":
        payload, err = save_doctor_response(body)
        return err or response(200, payload)

    match = re.fullmatch(r"/guide/([^/]+)", path)
    if method == "GET" and match:
        guide = get_guide(unquote_plus(match.group(1)))
        if not guide:
            return response(404, {"error": "session_not_found"})
        return response(200, guide)

    return response(404, {"error": "not_found", "method": method, "path": path})
