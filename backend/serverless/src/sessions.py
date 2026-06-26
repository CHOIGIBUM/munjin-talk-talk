"""DynamoDB 세션 저장소.

이 모듈은 문진 대기열과 세션 상태 조회에 필요한 최소 메타데이터만
DynamoDB에 저장합니다. 환자 발화, LLM 추출 결과, 원페이퍼, 환자 안내문은
`artifact_store.py`를 통해 S3에 저장하고, DynamoDB에는 S3 key와 상태만
남기는 구조를 지향합니다.
"""

from __future__ import annotations

import time
import uuid
import secrets
from typing import Any

from artifact_store import artifact_meta, delete_session_artifacts, load_answers, put_json, CONSENT_FILE
from privacy import consent_summary, sanitize_reception_patient
from question_sets import selected_question_set_id
from settings import table
from utils import ddb_value, mask_name, normalize_visit_type, now_iso

QUEUE_COUNTER_SESSION_ID = "__meta_queue_counter__"
DOCTOR_QUEUE_PRIORITY = {
    "needs_priority": 0,
    "waiting_doctor": 1,
    "completed": 1,
    "analysis_failed": 2,
    "analysis_pending": 3,
    "in_progress": 4,
    "staff_help": 5,
    "waiting_tablet": 6,
    "reviewed": 7,
}
DOCTOR_QUEUE_ARCHIVE_STATUSES = {"reviewed"}


def make_session_id() -> str:
    """새 문진 세션의 고유 ID를 만듭니다."""
    return f"s_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def make_patient_access() -> dict[str, Any]:
    """환자 태블릿에서 자기 세션에만 접근하기 위한 난수 토큰을 발급합니다."""
    return {
        "token": secrets.token_urlsafe(24),
        "issued_at": now_iso(),
        "scope": "patient_session",
    }


def get_session(session_id: str | None) -> dict[str, Any] | None:
    """session_id로 DynamoDB item을 조회합니다."""
    if not session_id:
        return None
    res = table.get_item(Key={"session_id": session_id})
    return res.get("Item")


def put_session(item: dict[str, Any]) -> dict[str, Any]:
    """DynamoDB에 item을 저장합니다."""
    converted = ddb_value(item)
    table.put_item(Item=converted)
    return converted


def _scan_max_queue_number() -> int:
    """기존 세션의 최대 대기번호를 읽어 counter 초기값으로 사용합니다."""
    try:
        res = table.scan(ProjectionExpression="queue_number", Limit=1000)
        numbers = [int(item.get("queue_number") or 0) for item in res.get("Items", [])]
        return max(numbers or [0])
    except Exception:
        return 0


def _visible_session_items() -> list[dict[str, Any]]:
    """Return non-meta session rows for queue calculations and list APIs."""
    res = table.scan(Limit=100)
    return [
        item for item in res.get("Items", [])
        if not str(item.get("session_id") or "").startswith("__meta")
    ]


def _numeric_queue_number(session: dict[str, Any]) -> int:
    try:
        value = int(session.get("queue_number") or 0)
        return value if value > 0 else 2**31
    except Exception:
        return 2**31


def _doctor_queue_sort_key(session: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        DOCTOR_QUEUE_PRIORITY.get(session.get("status", "waiting_tablet"), 9),
        _numeric_queue_number(session),
        str(session.get("created_at") or ""),
        str(session.get("session_id") or ""),
    )


def doctor_queue_position(session_id: str | None) -> int:
    """Return the current visible position in the doctor queue for one session.

    This mirrors the doctor queue ordering without exposing other patients to
    the tablet screen. Archived reviewed sessions are excluded from the number.
    """
    if not session_id:
        return 0
    try:
        active = [
            item for item in _visible_session_items()
            if item.get("status") not in DOCTOR_QUEUE_ARCHIVE_STATUSES
        ]
        active.sort(key=_doctor_queue_sort_key)
        for index, item in enumerate(active, start=1):
            if item.get("session_id") == session_id:
                return index
    except Exception:
        return 0
    return 0


def next_queue_number() -> int:
    """오늘 대기열 표시용 순번을 DynamoDB 원자 counter로 발급합니다.

    scan 후 max+1 방식은 동시 접수에서 같은 번호가 나올 수 있습니다.
    별도 meta item에 `ADD queue_counter :one`을 적용하면 DynamoDB가 증가를
    원자적으로 처리합니다. 실패 시에만 보수적인 보조 계산을 사용합니다.
    """
    try:
        try:
            table.put_item(
                Item={
                    "session_id": QUEUE_COUNTER_SESSION_ID,
                    "queue_counter": _scan_max_queue_number(),
                },
                ConditionExpression="attribute_not_exists(session_id)",
            )
        except Exception:
            # 이미 다른 요청이 counter를 만들었다면 정상 경합입니다.
            pass
        res = table.update_item(
            Key={"session_id": QUEUE_COUNTER_SESSION_ID},
            UpdateExpression="ADD queue_counter :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(res["Attributes"]["queue_counter"])
    except Exception:
        backup_number = _scan_max_queue_number()
        return backup_number + 1 if backup_number else int(time.time()) % 10000


def update_session(session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """DynamoDB item의 일부 필드만 SET expression으로 갱신합니다."""
    if not updates:
        return get_session(session_id)

    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    expr: list[str] = []
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


def delete_session(session_id: str) -> bool:
    """접수처에서 잘못 생성한 문진 세션을 삭제합니다.

    운영 세션만 삭제 대상으로 삼고, 대기번호 발급용 meta item은 보호합니다.
    S3 artifact 정리는 best-effort로 수행합니다. S3 삭제 권한이 부족하거나
    이미 객체가 없어 실패하더라도 DynamoDB 세션 삭제는 계속 진행합니다.
    """
    if not session_id or str(session_id).startswith("__meta"):
        return False

    session = get_session(session_id)
    if not session:
        return False

    try:
        delete_session_artifacts(session)
    except Exception as exc:
        print({
            "level": "warning",
            "event": "artifact_delete_failed",
            "session_id": session_id,
            "error": str(exc),
        })

    table.delete_item(Key={"session_id": session_id})
    return True


def create_session(body: dict[str, Any]) -> dict[str, Any]:
    """접수처 입력값으로 문진 세션을 생성합니다.

    실명, 생년월일, 연락처는 저장하지 않습니다. 생년월일은 나이 계산에만
    사용되고, 실명은 마스킹 표시명으로만 변환됩니다.
    """
    patient_input = body.get("patient") or body
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    question_set_id = str(body.get("question_set_id") or body.get("questionSetId") or selected_question_set_id())
    session_id = body.get("session_id") or body.get("sessionId") or make_session_id()
    created_at = now_iso()
    patient = sanitize_reception_patient(patient_input)
    if not patient.get("receipt_id"):
        patient["receipt_id"] = f"R-{int(time.time()) % 10000:04d}"

    item = {
        "session_id": session_id,
        "queue_number": body.get("queue_number") or body.get("queueNumber") or next_queue_number(),
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": int(time.time()) + 3 * 24 * 60 * 60,
        "status": "waiting_tablet",
        "visit_type": visit_type,
        "question_set_id": question_set_id,
        "risk": "none",
        "patient": patient,
        "patient_access": make_patient_access(),
        "artifact": artifact_meta(session_id, created_at),
        "question_status": {},
        "onepager_ready": False,
        "guide_ready": False,
    }
    return put_session(item)


def save_patient_consent(session_id: str, body: dict[str, Any]) -> dict[str, Any] | None:
    """환자 동의 상세는 S3에, 요약은 DynamoDB에 저장합니다."""
    session = get_session(session_id)
    if not session:
        return None

    accepted = bool(body.get("accepted"))
    now = now_iso()
    consent = {
        "accepted": accepted,
        "version": body.get("version") or "munjin-privacy-consent-v1",
        "method": "patient_tablet_modal",
        "recorded_at": now,
        "accepted_at": now if accepted else None,
        "rejected_at": now if not accepted else None,
        "privacy_items": body.get("privacy_items") or [],
        "sensitive_items": body.get("sensitive_items") or [],
        "retention_notice": body.get("retention_notice") or "문진 산출물은 MVP 운영 정책에 따라 임시 보관 후 삭제됩니다.",
    }
    put_json(session, CONSENT_FILE, consent)

    updates = {
        "privacy_consent": consent_summary(consent),
    }
    if accepted and session.get("status") == "consent_rejected":
        updates["status"] = "waiting_tablet"
    elif not accepted:
        updates["status"] = "consent_rejected"
    return update_session(session_id, updates)


def public_session(
    session: dict[str, Any],
    include_artifacts: bool = False,
    include_patient_token: bool = False,
    doctor_position: int | None = None,
) -> dict[str, Any]:
    """프론트엔드가 쓰는 세션 응답을 최소 필드 중심으로 반환합니다.

    대기열 목록에서는 artifact를 포함하지 않습니다. 직원 직접 입력처럼 세션
    상세가 필요한 API에서만 S3에 있는 가명처리 답변을 포함합니다.
    """
    patient = session.get("patient", {})
    # 과거 세션에는 두 글자 이름이 `김*윤`처럼 저장된 값이 있을 수 있습니다.
    # 신규 세션에는 v2 태그를 붙여 정상 3글자 마스킹(`홍*동`)은 유지하고,
    # 태그가 없는 기존 값만 더 엄격하게 보정합니다.
    repair_legacy_name = patient.get("name_mask_version") != "v2"
    patient_name = mask_name(
        patient.get("name") or patient.get("full_name"),
        repair_legacy_mask=repair_legacy_name,
    )
    payload = {
        "sessionId": session.get("session_id"),
        "session_id": session.get("session_id"),
        "queueNumber": session.get("queue_number") or 0,
        "doctorQueuePosition": int(doctor_position or 0),
        "doctor_queue_position": int(doctor_position or 0),
        "status": session.get("status", "waiting_tablet"),
        "visitType": session.get("visit_type", "initial"),
        "visit_type": session.get("visit_type", "initial"),
        "questionSetId": session.get("question_set_id", "default"),
        "question_set_id": session.get("question_set_id", "default"),
        "risk": session.get("risk", "none"),
        "onepagerReady": bool(session.get("onepager_ready")),
        "guideReady": bool(session.get("guide_ready")),
        "analysisStatus": session.get("analysis_status", ""),
        "analysis_status": session.get("analysis_status", ""),
        "analysisError": session.get("analysis_error", ""),
        "analysis_error": session.get("analysis_error", ""),
        "patient": {
            "name": patient_name or "환자",
            "age": patient.get("age", ""),
            "ageBand": patient.get("age_band", ""),
            "gender": patient.get("gender", "-"),
            "receiptId": patient.get("receipt_id", ""),
            "department": patient.get("department", "이비인후과"),
            "doctor": patient.get("doctor", ""),
            "honorific": patient.get("honorific", "환자님"),
        },
        "privacyConsent": session.get("privacy_consent", {}),
        "privacy_consent": session.get("privacy_consent", {}),
        "questionStatus": session.get("question_status", {}),
        "createdAt": session.get("created_at"),
        "updatedAt": session.get("updated_at"),
    }
    if include_artifacts:
        payload["responses"] = load_answers(session)
    if include_patient_token:
        token = (session.get("patient_access") or {}).get("token") or session.get("patient_token")
        if token:
            payload["patientToken"] = token
            payload["patient_token"] = token
    return payload


def list_sessions(include_patient_token: bool = False) -> list[dict[str, Any]]:
    """접수처와 의사 대기열에서 사용할 최신 세션 목록을 반환합니다."""
    items = _visible_session_items()
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return [public_session(item, include_patient_token=include_patient_token) for item in items]
