"""Questionnaire orchestration.

The patient-facing API must never wait for Bedrock/LangGraph analysis after Q4.
This module therefore splits the flow into two paths:

1. `/process-answers` stores the confirmed Q1-Q4 text, marks the session as
   `analysis_pending`, and asynchronously invokes the same Lambda.
2. The internal Lambda event runs the existing LangGraph pipeline, builds S3
   artifacts, and finally marks the session as `waiting_doctor` or
   `analysis_failed`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from artifact_store import load_answers, save_answers
from pipeline_graph import PIPELINE_GRAPH, run_answer_pipeline
from sessions import get_session, update_session
from utils import now_iso, response


INTERNAL_SOURCE = "munjin.analysis"
INTERNAL_ACTION_PROCESS_BATCH = "process_answers_batch"


def process_answer(body: dict[str, Any]):
    """Run the legacy single-question pipeline synchronously."""
    return run_answer_pipeline(body)


def process_answers(body: dict[str, Any]):
    """Accept the full patient questionnaire and enqueue analysis.

    The returned response is intentionally fast. Patient UX depends only on
    successful answer persistence, not on LLM extraction or IR completion.
    """
    session_id = body.get("session_id") or body.get("sessionId")
    visit_type = body.get("visit_type") or body.get("visitType")
    question_set_id = body.get("question_set_id") or body.get("questionSetId") or "default"
    answers = body.get("answers") or []

    if not session_id:
        return None, response(400, {"error": "missing_session_id"})
    if not isinstance(answers, list) or not answers:
        return None, response(400, {"error": "empty_answers"})

    session = get_session(session_id)
    if not session:
        return None, response(404, {"error": "session_not_found"})

    normalized_answers = []
    for index, answer in enumerate(answers, start=1):
        if not isinstance(answer, dict):
            return None, response(400, {"error": "invalid_answer_item", "index": index})
        item = normalize_batch_answer(answer, session_id, visit_type, question_set_id)
        if not item.get("question_id") or not str(item.get("transcript") or "").strip():
            return None, response(400, {"error": "invalid_answer_item", "index": index})
        normalized_answers.append(item)

    persist_pending_answers(session, normalized_answers)
    mark_analysis_pending(session_id, normalized_answers)

    enqueued, enqueue_error = enqueue_answer_analysis({
        "session_id": session_id,
        "visit_type": visit_type,
        "question_set_id": question_set_id,
        "answers": normalized_answers,
    })

    if not enqueued:
        update_session(session_id, {
            "status": "analysis_failed",
            "analysis_status": "enqueue_failed",
            "analysis_error": enqueue_error or "failed_to_enqueue_analysis",
            "analysis_updated_at": now_iso(),
        })

    return {
        "accepted": True,
        "patient_complete": True,
        "validator_passed": True,
        "onepager_ready": False,
        "analysis_status": "pending" if enqueued else "enqueue_failed",
        "analysis_queued": enqueued,
        "enqueue_error": enqueue_error,
        "results": [],
        "failed_results": [],
        "pipeline": {
            "graph": PIPELINE_GRAPH["name"],
            "mode": "queued_after_patient_confirmation",
            "queued_question_count": len(normalized_answers),
        },
    }, None


def retry_answer_analysis(session_id: str):
    """Queue a full analysis retry from already stored patient answers."""
    session = get_session(session_id)
    if not session:
        return None, response(404, {"error": "session_not_found"})

    answers_by_id = load_answers(session)
    normalized_answers = []
    for question_id in ("Q1", "Q2", "Q3", "Q4"):
        answer = answers_by_id.get(question_id)
        if not isinstance(answer, dict):
            continue
        transcript = answer.get("text") or answer.get("transcript") or ""
        if not str(transcript).strip():
            continue
        normalized_answers.append({
            "session_id": session_id,
            "visit_type": session.get("visit_type"),
            "question_set_id": session.get("question_set_id") or "default",
            "question_id": question_id,
            "question_type": answer.get("question_type") or answer.get("questionType") or "",
            "question_text": answer.get("question_text") or answer.get("questionText") or "",
            "transcript": transcript,
        })

    if not normalized_answers:
        return None, response(400, {"error": "no_answers_to_analyze"})

    mark_analysis_pending(session_id, normalized_answers)
    enqueued, enqueue_error = enqueue_answer_analysis({
        "session_id": session_id,
        "visit_type": session.get("visit_type"),
        "question_set_id": session.get("question_set_id") or "default",
        "answers": normalized_answers,
        "retry": True,
    })

    if not enqueued:
        update_session(session_id, {
            "status": "analysis_failed",
            "analysis_status": "enqueue_failed",
            "analysis_error": enqueue_error or "failed_to_enqueue_analysis",
            "analysis_updated_at": now_iso(),
        })
        return None, response(500, {"error": "failed_to_enqueue_analysis", "details": enqueue_error})

    return {
        "accepted": True,
        "analysis_status": "pending",
        "analysis_queued": True,
    }, None


def handle_internal_event(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Handle asynchronous Lambda self-invocation events."""
    if event.get("source") != INTERNAL_SOURCE or event.get("action") != INTERNAL_ACTION_PROCESS_BATCH:
        return {"ok": False, "error": "unknown_internal_event"}
    return run_queued_answer_analysis(event.get("payload") or {})


def run_queued_answer_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Run Q1-Q4 analysis after the patient has already completed the flow."""
    session_id = payload.get("session_id") or payload.get("sessionId")
    answers = payload.get("answers") or []
    if not session_id or not isinstance(answers, list) or not answers:
        return {"ok": False, "error": "invalid_analysis_payload"}

    update_session(session_id, {
        "analysis_status": "running",
        "analysis_started_at": now_iso(),
        "analysis_error": "",
    })

    try:
        result = run_answers_pipeline_sync(payload)
        failed = result.get("failed_results") or []
        onepager_ready = bool(result.get("onepager_ready"))
        final_status = "waiting_doctor" if onepager_ready else "analysis_failed"
        final_analysis_status = "partial_failed" if failed and onepager_ready else ("succeeded" if onepager_ready else "failed")
        update_session(session_id, {
            "status": final_status,
            "analysis_status": final_analysis_status,
            "analysis_completed_at": now_iso(),
            "analysis_error": "" if onepager_ready else "onepager_not_ready",
            "onepager_ready": onepager_ready,
            "analysis_failed_count": len(failed),
        })
        return {"ok": True, "analysis_status": final_analysis_status, "onepager_ready": onepager_ready}
    except Exception as exc:  # Lambda async event cannot surface errors to the patient.
        update_session(session_id, {
            "status": "analysis_failed",
            "analysis_status": "failed",
            "analysis_error": f"{exc.__class__.__name__}: {exc}",
            "analysis_completed_at": now_iso(),
            "onepager_ready": False,
        })
        print(json.dumps({
            "level": "error",
            "error": "queued_analysis_failed",
            "session_id": session_id,
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
        }, ensure_ascii=False))
        return {"ok": False, "error": "queued_analysis_failed", "exception_type": exc.__class__.__name__}


def run_answers_pipeline_sync(body: dict[str, Any]) -> dict[str, Any]:
    """Run the existing per-question LangGraph pipeline for an answer batch."""
    session_id = body.get("session_id") or body.get("sessionId")
    visit_type = body.get("visit_type") or body.get("visitType")
    question_set_id = body.get("question_set_id") or body.get("questionSetId") or "default"
    answers = body.get("answers") or []

    results = []
    failed_results = []
    for index, answer in enumerate(answers, start=1):
        item = normalize_batch_answer(answer, session_id, visit_type, question_set_id)
        payload, err = run_answer_pipeline(item)
        if err:
            status, err_body = unwrap_error_response(err)
            failed = {
                "question_id": item.get("question_id"),
                "question_type": item.get("question_type"),
                "transcript": item.get("transcript"),
                "status": status,
                "error": err_body.get("error") or "pipeline_error",
                "details": err_body,
                "batch_index": index,
            }
            failed_results.append(failed)
            results.append({
                "question_id": item.get("question_id"),
                "question_type": item.get("question_type"),
                "transcript": item.get("transcript"),
                "result": {
                    "validator_passed": False,
                    "error": failed["error"],
                    "details": err_body,
                },
            })
            continue

        results.append({
            "question_id": item.get("question_id"),
            "question_type": item.get("question_type"),
            "transcript": item.get("transcript"),
            "result": payload,
        })

    successful_results = [row for row in results if not row.get("result", {}).get("error")]
    return {
        "validator_passed": bool(results) and not failed_results and all(
            bool(row.get("result", {}).get("validator_passed")) for row in results
        ),
        "onepager_ready": any(bool(row.get("result", {}).get("onepager_ready")) for row in successful_results),
        "results": results,
        "failed_results": failed_results,
        "pipeline": {
            "graph": PIPELINE_GRAPH["name"],
            "mode": "async_batch_after_patient_confirmation",
            "processed_question_count": len(results),
            "failed_question_count": len(failed_results),
        },
    }


def enqueue_answer_analysis(payload: dict[str, Any]) -> tuple[bool, str]:
    """Invoke this Lambda asynchronously for background analysis."""
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        return False, "missing_lambda_function_name"
    try:
        boto3.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({
                "source": INTERNAL_SOURCE,
                "action": INTERNAL_ACTION_PROCESS_BATCH,
                "payload": payload,
            }, ensure_ascii=False).encode("utf-8"),
        )
        return True, ""
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def persist_pending_answers(session: dict[str, Any], answers: list[dict[str, Any]]) -> None:
    """Store confirmed patient text before any LLM processing starts."""
    stored = load_answers(session)
    for item in answers:
        question_id = item.get("question_id")
        stored[question_id] = {
            "text": item.get("transcript") or "",
            "question_type": item.get("question_type") or "",
            "question_text": item.get("question_text") or "",
            "analysis_status": "pending",
            "spans": [],
            "matched_slots": [],
            "structured": {},
            "confirmed": True,
        }
    save_answers(session, stored)


def mark_analysis_pending(session_id: str, answers: list[dict[str, Any]]) -> None:
    """Move session to doctor-waiting pipeline state without waiting for LLM."""
    session = get_session(session_id) or {}
    question_status = dict(session.get("question_status") or {})
    for item in answers:
        question_status[item.get("question_id")] = {
            "answered": True,
            "analysis_status": "pending",
            "method": "queued_batch",
        }
    update_session(session_id, {
        "status": "analysis_pending",
        "analysis_status": "pending",
        "analysis_requested_at": now_iso(),
        "analysis_error": "",
        "question_status": question_status,
        "onepager_ready": False,
    })


def normalize_batch_answer(answer: dict[str, Any], session_id: str, visit_type: str, question_set_id: str) -> dict[str, Any]:
    """Normalize camelCase/snake_case frontend fields for the pipeline."""
    return {
        "session_id": session_id,
        "visit_type": visit_type,
        "question_set_id": answer.get("question_set_id") or answer.get("questionSetId") or question_set_id,
        "question_id": answer.get("question_id") or answer.get("questionId") or answer.get("id"),
        "question_type": answer.get("question_type") or answer.get("questionType"),
        "question_text": answer.get("question_text") or answer.get("questionText") or "",
        "transcript": answer.get("transcript") or answer.get("text") or "",
    }


def unwrap_error_response(err: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Convert a Lambda-style error response into a compact dict."""
    status = int(err.get("statusCode") or 500)
    try:
        body = json.loads(err.get("body") or "{}")
    except json.JSONDecodeError:
        body = {"error": "pipeline_error"}
    if not isinstance(body, dict):
        body = {"error": "pipeline_error"}
    return status, body
