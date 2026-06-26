"""Queued analysis continuation tests."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import orchestration  # noqa: E402


class LowTimeContext:
    def get_remaining_time_in_millis(self):
        return 10_000


def test_run_answers_pipeline_requeues_remaining_answers_when_time_is_low(monkeypatch):
    captured = {}

    def fake_run_answer_pipeline(item):
        return {
            "validator_passed": True,
            "onepager_ready": item["question_id"] == "Q4",
        }, None

    def fake_enqueue(payload):
        captured["payload"] = payload
        return True, ""

    monkeypatch.setattr(orchestration, "run_answer_pipeline", fake_run_answer_pipeline)
    monkeypatch.setattr(orchestration, "enqueue_answer_analysis", fake_enqueue)

    result = orchestration.run_answers_pipeline_sync(
        {
            "session_id": "s-test",
            "visit_type": "initial",
            "question_set_id": "default",
            "answers": [
                {"question_id": "Q1", "question_type": "chief_complaint", "transcript": "기침이 나"},
                {"question_id": "Q2", "question_type": "onset", "transcript": "어제부터"},
                {"question_id": "Q4", "question_type": "patient_questions", "transcript": "약 같이 먹어도 돼?"},
            ],
        },
        LowTimeContext(),
    )

    assert result["continuation_queued"] is True
    assert result["processed_question_count"] == 1
    assert result["remaining_question_count"] == 2
    assert [item["question_id"] for item in captured["payload"]["answers"]] == ["Q2", "Q4"]
    assert captured["payload"]["continuation"] is True
    assert captured["payload"]["previous_processed_question_count"] == 1


def test_run_queued_analysis_preserves_priority_status(monkeypatch):
    updates = []

    monkeypatch.setattr(orchestration, "update_session", lambda _session_id, update: updates.append(update))
    monkeypatch.setattr(orchestration, "get_session", lambda _session_id: {"risk": "high", "status": "needs_priority"})
    monkeypatch.setattr(
        orchestration,
        "run_answers_pipeline_sync",
        lambda _payload, _context=None: {
            "onepager_ready": True,
            "failed_results": [],
            "pipeline": {"failed_question_count": 0},
        },
    )

    result = orchestration.run_queued_answer_analysis(
        {
            "session_id": "s-test",
            "answers": [{"question_id": "Q4", "question_type": "patient_questions", "transcript": "궁금해"}],
        }
    )

    assert result["ok"] is True
    assert updates[-1]["status"] == "needs_priority"
    assert updates[-1]["analysis_status"] == "succeeded"
