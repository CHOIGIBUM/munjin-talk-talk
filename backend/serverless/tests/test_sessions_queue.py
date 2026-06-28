"""DynamoDB 대기번호 원자 counter 테스트."""

from __future__ import annotations

import importlib
import pytest
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakeTable:
    """sessions.py가 사용하는 DynamoDB Table 메서드만 구현한 테스트 더블."""

    def __init__(self):
        self.items = {
            "s_old": {
                "session_id": "s_old",
                "queue_number": 7,
                "service_date": "2000-01-01",
                "created_at": "2000-01-01T00:00:00+00:00",
                "updated_at": "2000-01-01T00:00:00+00:00",
                "patient": {"name": "김*자", "receipt_id": "R-0001"},
            }
        }

    def get_item(self, Key):
        item = self.items.get(Key["session_id"])
        return {"Item": item} if item else {}

    def put_item(self, Item, ConditionExpression=None):
        key = Item["session_id"]
        if ConditionExpression and key in self.items:
            raise RuntimeError("conditional check failed")
        self.items[key] = dict(Item)

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, **_kwargs):
        key = Key["session_id"]
        item = self.items.setdefault(key, {"session_id": key, "queue_counter": 0})
        if UpdateExpression.startswith("ADD queue_counter"):
            item["queue_counter"] = int(item.get("queue_counter") or 0) + int(ExpressionAttributeValues[":one"])
            return {"Attributes": {"queue_counter": item["queue_counter"]}}
        if UpdateExpression.startswith("SET "):
            names = _kwargs.get("ExpressionAttributeNames") or {}
            assignments = UpdateExpression.removeprefix("SET ").split(", ")
            for assignment in assignments:
                name_key, value_key = [part.strip() for part in assignment.split(" = ", 1)]
                item[names.get(name_key, name_key)] = ExpressionAttributeValues[value_key]
            return {"Attributes": dict(item)}
        raise AssertionError(f"Unexpected update expression: {UpdateExpression}")

    def scan(self, **_kwargs):
        return {"Items": list(self.items.values())}

    def delete_item(self, Key):
        self.items.pop(Key["session_id"], None)


def import_sessions_with_fake_table(fake_table: FakeTable):
    """sessions 모듈이 AWS 클라이언트를 만들지 않도록 의존 모듈을 가짜로 주입합니다."""
    for name in ["settings", "artifact_store", "privacy", "sessions"]:
        sys.modules.pop(name, None)

    settings = types.ModuleType("settings")
    settings.table = fake_table
    sys.modules["settings"] = settings

    artifact_store = types.ModuleType("artifact_store")
    artifact_store.CONSENT_FILE = "consent.json"
    artifact_store.artifact_meta = lambda session_id, created_at: {"session_id": session_id, "created_at": created_at}
    artifact_store.load_answers = lambda _session: {}
    artifact_store.put_json = lambda *_args, **_kwargs: None
    artifact_store.delete_session_artifacts = lambda _session: None
    sys.modules["artifact_store"] = artifact_store

    privacy = types.ModuleType("privacy")
    privacy.consent_summary = lambda consent: {"accepted": bool(consent.get("accepted"))}
    privacy.sanitize_reception_patient = lambda patient: dict(patient or {})
    sys.modules["privacy"] = privacy

    return importlib.import_module("sessions")


def test_queue_counter_is_atomic_and_meta_session_is_hidden():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)
    today = sessions.current_service_date()
    fake.items["s_today"] = {
        "session_id": "s_today",
        "status": "waiting_tablet",
        "service_date": today,
        "queue_number": 7,
        "created_at": f"{today}T00:00:00+09:00",
        "patient": {"name": "오*늘", "age": 70, "receipt_id": "R-0003"},
    }

    assert sessions.next_queue_number() == 8
    assert sessions.next_queue_number() == 9
    assert fake.items[sessions.queue_counter_session_id(today)]["queue_counter"] == 9

    visible = sessions.list_sessions()

    assert visible
    assert all(not item["sessionId"].startswith("__meta") for item in visible)
    assert [item["sessionId"] for item in visible] == ["s_today"]


def test_daily_queue_counter_starts_from_one_when_only_old_sessions_exist():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)

    assert sessions.next_queue_number() == 1


def test_create_session_stores_question_set_id():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)

    created = sessions.create_session({
        "visit_type": "initial",
        "question_set_id": "default",
        "queue_number": 12,
        "patient": {"name": "김철수", "age": 70, "receipt_id": "R-0002"},
    })

    assert created["question_set_id"] == "default"
    assert sessions.public_session(created)["questionSetId"] == "default"
    assert created["service_date"] == sessions.current_service_date()


def test_create_session_rejects_placeholder_patient_name():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)

    with pytest.raises(ValueError, match="patient_name_required"):
        sessions.create_session({
            "visit_type": "initial",
            "patient": {"name": "환자", "age": 70},
        })


def test_create_session_rejects_missing_birth_or_age():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)

    with pytest.raises(ValueError, match="patient_birth_date_required"):
        sessions.create_session({
            "visit_type": "initial",
            "patient": {"name": "김철수"},
        })


def test_doctor_queue_position_matches_active_queue_order():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)
    fake.items.update({
        "s_priority": {
            "session_id": "s_priority",
            "status": "needs_priority",
            "service_date": sessions.current_service_date(),
            "queue_number": 50,
            "created_at": "2026-06-01T00:02:00",
            "patient": {"name": "우*선"},
        },
        "s_ready": {
            "session_id": "s_ready",
            "status": "waiting_doctor",
            "service_date": sessions.current_service_date(),
            "queue_number": 20,
            "created_at": "2026-06-01T00:03:00",
            "patient": {"name": "대*기"},
        },
        "s_pending": {
            "session_id": "s_pending",
            "status": "analysis_pending",
            "service_date": sessions.current_service_date(),
            "queue_number": 30,
            "created_at": "2026-06-01T00:04:00",
            "patient": {"name": "분*석"},
        },
        "s_archived": {
            "session_id": "s_archived",
            "status": "reviewed",
            "service_date": sessions.current_service_date(),
            "queue_number": 1,
            "created_at": "2026-06-01T00:05:00",
            "patient": {"name": "완*료"},
        },
    })

    assert sessions.doctor_queue_position("s_pending") == 3
    assert sessions.doctor_queue_position("s_archived") == 0
    assert sessions.public_session(fake.items["s_pending"], doctor_position=3)["doctorQueuePosition"] == 3


def test_delete_session_removes_user_session_but_not_meta_counter():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)

    assert sessions.delete_session("s_old") is True
    assert "s_old" not in fake.items
    assert sessions.delete_session(sessions.QUEUE_COUNTER_SESSION_ID) is False


def test_accepting_after_rejection_reopens_tablet_flow():
    fake = FakeTable()
    sessions = import_sessions_with_fake_table(fake)
    fake.items["s_old"]["status"] = "consent_rejected"

    updated = sessions.save_patient_consent("s_old", {"accepted": True, "version": "v-test"})

    assert updated["privacy_consent"] == {"accepted": True}
    assert updated["status"] == "waiting_tablet"
