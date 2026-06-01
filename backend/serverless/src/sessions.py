"""DynamoDB session repository.

환자 1명의 문진 전체 상태는 MunjinSessions 테이블의 item 하나에 누적됩니다.
이 모듈은 세션 생성, 조회, 업데이트, 프론트 공개용 변환만 담당합니다.
"""

import time
import uuid

from settings import table
from utils import calculate_age, ddb_value, mask_name, normalize_visit_type, now_iso


def make_session_id():
    """새 문진 세션의 고유 ID를 만듭니다."""
    return f"s_{int(time.time())}_{uuid.uuid4().hex[:8]}"

def get_session(session_id):
    """session_id로 DynamoDB item을 조회합니다."""
    if not session_id:
        return None
    res = table.get_item(Key={"session_id": session_id})
    return res.get("Item")


def put_session(item):
    converted = ddb_value(item)
    table.put_item(Item=converted)
    return converted


def next_queue_number():
    try:
        res = table.scan(ProjectionExpression="queue_number", Limit=1000)
        numbers = [int(item.get("queue_number") or 0) for item in res.get("Items", [])]
        return max(numbers or [0]) + 1
    except Exception:
        return int(time.time()) % 10000


def update_session(session_id, updates):
    """부분 업데이트를 안전하게 SET expression으로 반영합니다."""
    if not updates:
        return get_session(session_id)
    names = {}
    values = {}
    expr = []
    for idx, (key, value) in enumerate(updates.items()):
        nk = f"#k{idx}"
        vk = f":v{idx}"
        names[nk] = key
        values[vk] = ddb_value(value)
        expr.append(f"{nk} = {vk}")
    names["#updated_at"] = "updated_at"
    values[":updated_at"] = now_iso()
    expr.append("#updated_at = :updated_at")
    res = table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET " + ", ".join(expr),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return res.get("Attributes")


def create_session(body):
    """접수처 입력값으로 새 문진 세션을 만들고 초기 onepager 뼈대를 저장합니다."""
    patient_input = body.get("patient") or body
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    full_name = patient_input.get("full_name") or patient_input.get("fullName") or patient_input.get("name") or ""
    birth_date = patient_input.get("birth_date") or patient_input.get("birthDate") or ""
    patient = {
        "name": mask_name(full_name),
        "full_name": full_name,
        "birth_date": birth_date,
        "age": patient_input.get("age") or calculate_age(birth_date),
        "gender": patient_input.get("gender") or "-",
        "receipt_id": patient_input.get("receipt_id") or patient_input.get("receiptId") or f"R-{int(time.time()) % 10000:04d}",
        "department": patient_input.get("department") or "이비인후과",
        "doctor": patient_input.get("doctor") or "이민우",
        "phone": patient_input.get("phone") or "",
    }
    session_id = body.get("session_id") or body.get("sessionId") or make_session_id()
    from onepager import build_onepager

    item = {
        "session_id": session_id,
        "queue_number": body.get("queue_number") or body.get("queueNumber") or next_queue_number(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "waiting_tablet",
        "visit_type": visit_type,
        "risk": "none",
        "patient": patient,
        "responses": {},
        "question_results": {},
        "audio": {},
        "onepager": build_onepager({
            "session_id": session_id,
            "visit_type": visit_type,
            "patient": patient,
            "responses": {},
            "question_results": {},
            "risk": "none",
        }),
    }
    return put_session(item)


def public_session(session):
    """프론트 목록/라우팅에 필요한 최소 필드와 camelCase 호환 필드를 반환합니다."""
    patient = session.get("patient", {})
    return {
        "sessionId": session.get("session_id"),
        "session_id": session.get("session_id"),
        "queueNumber": session.get("queue_number") or 0,
        "status": session.get("status", "waiting_tablet"),
        "visitType": session.get("visit_type", "initial"),
        "visit_type": session.get("visit_type", "initial"),
        "risk": session.get("risk", "none"),
        "patient": {
            "name": patient.get("name") or mask_name(patient.get("full_name")),
            "fullName": patient.get("full_name", ""),
            "birthDate": patient.get("birth_date", ""),
            "age": patient.get("age", ""),
            "gender": patient.get("gender", "-"),
            "receiptId": patient.get("receipt_id", ""),
            "department": patient.get("department", "이비인후과"),
            "doctor": patient.get("doctor", ""),
            "phone": patient.get("phone", ""),
            "honorific": "어르신",
        },
        "responses": session.get("responses", {}),
        "createdAt": session.get("created_at"),
        "updatedAt": session.get("updated_at"),
    }


def list_sessions():
    """접수처와 의사 대기열에서 사용할 최근 세션 목록을 반환합니다."""
    res = table.scan(Limit=100)
    items = res.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return [public_session(item) for item in items]
