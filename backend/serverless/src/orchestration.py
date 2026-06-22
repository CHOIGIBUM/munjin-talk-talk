"""Question processing orchestration.

프론트엔드가 확인된 환자 발화 1개를 보내면 이 모듈이 LangGraph 기반
파이프라인을 실행합니다. 실제 노드 정의는 `pipeline_graph.py`에 있고,
이 파일은 기존 handler/import 계약을 유지하는 얇은 진입점 역할만 합니다.
"""

import json

from pipeline_graph import PIPELINE_GRAPH, run_answer_pipeline
from utils import response


def process_answer(body):
    """환자 답변 1개를 LangGraph 파이프라인으로 처리합니다."""
    return run_answer_pipeline(body)


def process_answers(body):
    """Q1~Q4 답변을 모두 받은 뒤 서버에서 순서대로 처리합니다.

    환자 화면은 각 문항에서 STT 텍스트 확인만 수행하고, 마지막 문항에서 이
    batch API를 한 번 호출합니다. 실제 처리 로직은 기존 단일 문항
    LangGraph 파이프라인을 그대로 재사용하므로 원페이퍼/안내문 저장 구조는
    바뀌지 않습니다.
    """
    session_id = body.get("session_id") or body.get("sessionId")
    visit_type = body.get("visit_type") or body.get("visitType")
    question_set_id = body.get("question_set_id") or body.get("questionSetId") or "default"
    answers = body.get("answers") or []

    if not session_id:
        return None, response(400, {"error": "missing_session_id"})
    if not isinstance(answers, list) or not answers:
        return None, response(400, {"error": "empty_answers"})

    results = []
    failed_results = []
    for index, answer in enumerate(answers, start=1):
        if not isinstance(answer, dict):
            return None, response(400, {"error": "invalid_answer_item", "index": index})

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
            # 한 문항 분석 실패가 환자 문진 전체를 되감지 않도록 다음 문항 처리를 계속한다.
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
            "mode": "batch_after_patient_confirmation",
            "processed_question_count": len(results),
            "failed_question_count": len(failed_results),
        },
    }, None


def normalize_batch_answer(answer, session_id, visit_type, question_set_id):
    """camelCase/snake_case 입력을 기존 단일 문항 파이프라인 입력으로 통일합니다."""
    return {
        "session_id": session_id,
        "visit_type": visit_type,
        "question_set_id": answer.get("question_set_id") or answer.get("questionSetId") or question_set_id,
        "question_id": answer.get("question_id") or answer.get("questionId") or answer.get("id"),
        "question_type": answer.get("question_type") or answer.get("questionType"),
        "question_text": answer.get("question_text") or answer.get("questionText") or "",
        "transcript": answer.get("transcript") or answer.get("text") or "",
    }


def unwrap_error_response(err):
    """단일 문항 처리 오류 응답을 batch 오류 본문으로 재사용합니다."""
    status = int(err.get("statusCode") or 500)
    try:
        body = json.loads(err.get("body") or "{}")
    except json.JSONDecodeError:
        body = {"error": "pipeline_error"}
    if not isinstance(body, dict):
        body = {"error": "pipeline_error"}
    return status, body
