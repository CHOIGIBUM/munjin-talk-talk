"""LangGraph answer-processing pipeline.

이 파일은 환자 답변 1개가 백엔드에서 지나가는 실제 처리 흐름을
LangGraph 노드로 명시합니다. 각 노드는 "무엇을 입력받아 무엇을 남겼는지"를
trace에 기록하므로, DynamoDB와 API 응답에서 처리 과정을 사람이 확인할 수 있습니다.
"""

from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from clinical_terms import find_safety_flag
from extraction import extract_question
from onepager import validate_and_save
from retrieval import match_slots
from utils import normalize_visit_type, response


SYMPTOM_QUESTION_TYPES = {"chief_complaint", "progress", "new_symptoms"}


class AnswerPipelineState(TypedDict, total=False):
    """LangGraph가 노드 사이에서 전달하는 상태 객체입니다."""

    body: dict[str, Any]
    session_id: str
    question_id: str
    question_type: str
    visit_type: str
    transcript: str
    preliminary_safety_flag: dict[str, Any] | None
    extracted: dict[str, Any]
    matched: dict[str, Any]
    validated: dict[str, Any]
    semantic_failed: bool
    safety_only: bool
    error_response: dict[str, Any]
    result_payload: dict[str, Any]
    active_path: list[str]
    trace: list[dict[str, Any]]


PIPELINE_GRAPH = {
    "name": "munjin_langgraph_answer_pipeline",
    "version": "v1",
    "nodes": [
        "input_transcript",
        "quick_safety_flag",
        "semantic_extraction",
        "schema_quote_validation",
        "hybrid_ir_match",
        "session_validation_save",
        "safety_guardrail_save",
        "onepaper_refresh",
        "response_payload",
    ],
    "edges": [
        ["__start__", "input_transcript"],
        ["input_transcript", "quick_safety_flag"],
        ["quick_safety_flag", "semantic_extraction"],
        ["semantic_extraction", "schema_quote_validation"],
        ["schema_quote_validation", "hybrid_ir_match"],
        ["schema_quote_validation", "safety_guardrail_save"],
        ["hybrid_ir_match", "session_validation_save"],
        ["session_validation_save", "onepaper_refresh"],
        ["safety_guardrail_save", "onepaper_refresh"],
        ["onepaper_refresh", "response_payload"],
        ["response_payload", "__end__"],
    ],
    "retry_policy": {
        "semantic_extraction": "EXTRACTION_RETRY_ATTEMPTS",
        "onepaper_final_review": "REVIEW_RETRY_ATTEMPTS",
    },
}


def run_answer_pipeline(body: dict[str, Any]):
    """LangGraph를 실행하고 기존 handler 계약에 맞게 (payload, error)를 반환합니다."""
    final_state = _compiled_graph().invoke({"body": body or {}, "trace": [], "active_path": []})
    if final_state.get("error_response"):
        return None, final_state["error_response"]
    return final_state.get("result_payload") or {}, None


def pipeline_graph_description() -> dict[str, Any]:
    """프론트/문서/응답에서 재사용할 수 있는 그래프 설명입니다."""
    return dict(PIPELINE_GRAPH)


def input_transcript_node(state: AnswerPipelineState) -> dict[str, Any]:
    """요청 payload를 표준 필드로 정리하고 필수값을 검증합니다."""
    body = state.get("body") or {}
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    question_type = body.get("question_type") or body.get("questionType")
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    transcript = (body.get("transcript") or "").strip()

    update: dict[str, Any] = {
        "session_id": session_id,
        "question_id": question_id,
        "question_type": question_type,
        "visit_type": visit_type,
        "transcript": transcript,
    }
    if not session_id or not question_id or not question_type:
        update["error_response"] = response(400, {"error": "missing_required_fields"})
        update.update(_trace(state, "input_transcript", "failed", {"reason": "missing_required_fields"}))
        return update
    if not transcript:
        update["error_response"] = response(400, {"error": "empty_transcript"})
        update.update(_trace(state, "input_transcript", "failed", {"reason": "empty_transcript"}))
        return update

    update.update(
        _trace(
            state,
            "input_transcript",
            "passed",
            {
                "question_id": question_id,
                "question_type": question_type,
                "visit_type": visit_type,
                "transcript_chars": len(transcript),
            },
        )
    )
    return update


def quick_safety_flag_node(state: AnswerPipelineState) -> dict[str, Any]:
    """LLM 호출 전 즉시 위험 표현을 먼저 감지합니다."""
    safety_flag = find_safety_flag(state.get("transcript") or "", [])
    update = {"preliminary_safety_flag": safety_flag}
    update.update(
        _trace(
            state,
            "quick_safety_flag",
            "flagged" if safety_flag else "clear",
            {
                "has_flag": bool(safety_flag),
                "flag_type": (safety_flag or {}).get("type"),
                "matched_pattern": (safety_flag or {}).get("matched_pattern"),
            },
        )
    )
    return update


def semantic_extraction_node(state: AnswerPipelineState) -> dict[str, Any]:
    """Bedrock LLM으로 의미 단위 분할, 표준화, 고정 스키마 출력을 수행합니다."""
    body = {
        **(state.get("body") or {}),
        "session_id": state.get("session_id"),
        "question_id": state.get("question_id"),
        "question_type": state.get("question_type"),
        "visit_type": state.get("visit_type"),
        "transcript": state.get("transcript"),
    }
    extracted = extract_question(body)
    llm_meta = extracted.get("llm_meta") or {}
    semantic_failed = extracted.get("validator_passed") is False or extracted.get("method") in {
        "bedrock_error",
        "bedrock_disabled",
    }
    update = {"extracted": extracted, "semantic_failed": semantic_failed}
    update.update(
        _trace(
            state,
            "semantic_extraction",
            "failed" if semantic_failed else "passed",
            {
                "method": extracted.get("method"),
                "model_id": llm_meta.get("model_id"),
                "attempts": llm_meta.get("attempts"),
                "validation_error_count": len(llm_meta.get("validation_errors") or []),
                "span_count": len(extracted.get("spans") or []),
                "structured_keys": sorted((extracted.get("structured") or {}).keys()),
            },
        )
    )
    return update


def schema_quote_validation_node(state: AnswerPipelineState) -> dict[str, Any]:
    """LLM 출력이 스키마와 원문 quote 검증을 통과했는지 분기합니다."""
    extracted = state.get("extracted") or {}
    if state.get("semantic_failed"):
        safety_flag = state.get("preliminary_safety_flag")
        if safety_flag:
            update = {"safety_only": True}
            update.update(
                _trace(
                    state,
                    "schema_quote_validation",
                    "safety_branch",
                    {
                        "reason": "semantic_extraction_failed_but_safety_flag_exists",
                        "llm_error": extracted.get("error"),
                    },
                )
            )
            return update
        update = {
            "error_response": response(
                422,
                {
                    "error": "semantic_extraction_failed",
                    "message": extracted.get("error") or "LLM schema/quote validation failed after retries.",
                    "llm_meta": extracted.get("llm_meta") or {},
                },
            )
        }
        update.update(
            _trace(
                state,
                "schema_quote_validation",
                "failed",
                {
                    "reason": "validator_failed_without_safety_flag",
                    "llm_error": extracted.get("error"),
                },
            )
        )
        return update

    update = {"safety_only": False}
    update.update(
        _trace(
            state,
            "schema_quote_validation",
            "passed",
            {
                "validator_passed": bool(extracted.get("validator_passed")),
                "retry_loop": (extracted.get("llm_meta") or {}).get("retry_loop"),
            },
        )
    )
    return update


def hybrid_ir_match_node(state: AnswerPipelineState) -> dict[str, Any]:
    """증상 문항이면 BM25 + Titan Vector IR로 표준 증상명에 매칭합니다."""
    question_type = state.get("question_type")
    if question_type not in SYMPTOM_QUESTION_TYPES:
        matched = {"matched_slots": [], "unmatched_spans": []}
        update = {"matched": matched}
        update.update(_trace(state, "hybrid_ir_match", "skipped", {"question_type": question_type}))
        return update

    extracted = state.get("extracted") or {}
    matched = match_slots(
        {
            "session_id": state.get("session_id"),
            "question_id": state.get("question_id"),
            "visit_type": state.get("visit_type"),
            "spans": extracted.get("spans", []),
        }
    )
    update = {"matched": matched}
    update.update(
        _trace(
            state,
            "hybrid_ir_match",
            "matched",
            {
                "matched_count": len(matched.get("matched_slots") or []),
                "unmatched_count": len(matched.get("unmatched_spans") or []),
                "method": "bm25_titan_hybrid",
            },
        )
    )
    return update


def session_validation_save_node(state: AnswerPipelineState) -> dict[str, Any]:
    """검증된 문항 결과를 DynamoDB에 저장하고 onepaper를 갱신합니다."""
    extracted = state.get("extracted") or {}
    matched = state.get("matched") or {"matched_slots": [], "unmatched_spans": []}
    save_trace = _next_trace_entry(
        state,
        "session_validation_save",
        "saving",
        {"matched_count": len(matched.get("matched_slots") or [])},
    )
    validated, err = validate_and_save(
        {
            "session_id": state.get("session_id"),
            "question_id": state.get("question_id"),
            "question_type": state.get("question_type"),
            "visit_type": state.get("visit_type"),
            "transcript": state.get("transcript"),
            "spans": extracted.get("spans", []),
            "matched_slots": matched.get("matched_slots", []),
            "structured": extracted.get("structured", {}),
            "method": extracted.get("method"),
            "llm_meta": extracted.get("llm_meta") or {},
            "orchestration": _orchestration_snapshot(state, save_trace),
            "pipeline_trace": save_trace,
        }
    )
    if err:
        update = {"error_response": err}
        update.update(_trace(state, "session_validation_save", "failed", {"reason": "validate_and_save_error"}))
        return update

    update = {"validated": validated}
    update.update(
        _trace(
            state,
            "session_validation_save",
            "saved",
            {
                "validator_passed": bool(validated.get("validator_passed")),
                "onepager_ready": bool(validated.get("onepager_ready")),
                "has_safety_flag": bool(validated.get("safety_flag")),
            },
        )
    )
    return update


def safety_guardrail_save_node(state: AnswerPipelineState) -> dict[str, Any]:
    """LLM 검증 실패 중에도 안전 플래그는 누락되지 않도록 별도 저장합니다."""
    extracted = state.get("extracted") or {}
    safety_flag = state.get("preliminary_safety_flag") or {}
    transcript = state.get("transcript") or ""
    structured = {
        "standardized_text": transcript,
        "clinical_clues": [],
        "questions": [],
        "unresolved_items": [
            {
                "source_quote": safety_flag.get("matched_pattern") or transcript,
                "summary": "안전 플래그 감지 후 LLM 의미 추출 검증에 실패했습니다.",
            }
        ],
    }
    save_trace = _next_trace_entry(
        state,
        "safety_guardrail_save",
        "saving",
        {"matched_pattern": safety_flag.get("matched_pattern")},
    )
    validated, err = validate_and_save(
        {
            **(state.get("body") or {}),
            "session_id": state.get("session_id"),
            "question_id": state.get("question_id"),
            "question_type": state.get("question_type"),
            "visit_type": state.get("visit_type"),
            "transcript": transcript,
            "spans": [],
            "matched_slots": [],
            "structured": structured,
            "method": extracted.get("method") or "safety_guardrail_only",
            "llm_meta": {
                **(extracted.get("llm_meta") or {}),
                "semantic_extraction_failed": True,
                "safety_saved_without_extraction": True,
            },
            "orchestration": _orchestration_snapshot(state, save_trace),
            "pipeline_trace": save_trace,
        }
    )
    if err:
        update = {"error_response": err}
        update.update(_trace(state, "safety_guardrail_save", "failed", {"reason": "validate_and_save_error"}))
        return update

    update = {"validated": validated, "matched": {"matched_slots": [], "unmatched_spans": []}}
    update.update(
        _trace(
            state,
            "safety_guardrail_save",
            "saved",
            {
                "validator_passed": True,
                "has_safety_flag": bool(validated.get("safety_flag") or safety_flag),
            },
        )
    )
    return update


def onepaper_refresh_node(state: AnswerPipelineState) -> dict[str, Any]:
    """저장 단계에서 갱신된 onepaper 상태를 trace에 명시합니다."""
    validated = state.get("validated") or {}
    update: dict[str, Any] = {}
    update.update(
        _trace(
            state,
            "onepaper_refresh",
            "refreshed",
            {
                "onepager_ready": bool(validated.get("onepager_ready")),
                "refresh_source": "validate_and_save",
            },
        )
    )
    return update


def response_payload_node(state: AnswerPipelineState) -> dict[str, Any]:
    """프론트엔드가 받는 최종 응답 payload를 조립합니다."""
    extracted = state.get("extracted") or {}
    matched = state.get("matched") or {"matched_slots": [], "unmatched_spans": []}
    validated = state.get("validated") or {}
    final_trace = _next_trace_entry(
        state,
        "response_payload",
        "completed",
        {"question_id": state.get("question_id")},
    )
    _persist_final_trace(state, final_trace)
    payload = {
        "spans": extracted.get("spans", []),
        "structured": extracted.get("structured", {}),
        "matched_slots": matched.get("matched_slots", []),
        "unmatched_spans": matched.get("unmatched_spans", []),
        "validator_passed": bool(validated.get("validator_passed")),
        "safety_flag": validated.get("safety_flag") or state.get("preliminary_safety_flag"),
        "errors": _response_errors(state),
        "onepager_ready": validated.get("onepager_ready", False),
        "orchestration": _orchestration_snapshot(state, final_trace),
    }
    update = {"result_payload": payload}
    update["trace"] = final_trace
    update["active_path"] = [*state.get("active_path", []), "response_payload"]
    return update


def route_after_required_input(state: AnswerPipelineState) -> str:
    return "stop" if state.get("error_response") else "continue"


def route_after_schema_validation(state: AnswerPipelineState) -> str:
    if state.get("error_response"):
        return "stop"
    if state.get("safety_only"):
        return "safety"
    return "continue"


def route_after_save(state: AnswerPipelineState) -> str:
    return "stop" if state.get("error_response") else "continue"


def _compiled_graph():
    """Lambda warm invocation에서 재사용할 수 있도록 graph를 한 번만 compile합니다."""
    if not hasattr(_compiled_graph, "_graph"):
        workflow = StateGraph(AnswerPipelineState)
        workflow.add_node("input_transcript", input_transcript_node)
        workflow.add_node("quick_safety_flag", quick_safety_flag_node)
        workflow.add_node("semantic_extraction", semantic_extraction_node)
        workflow.add_node("schema_quote_validation", schema_quote_validation_node)
        workflow.add_node("hybrid_ir_match", hybrid_ir_match_node)
        workflow.add_node("session_validation_save", session_validation_save_node)
        workflow.add_node("safety_guardrail_save", safety_guardrail_save_node)
        workflow.add_node("onepaper_refresh", onepaper_refresh_node)
        workflow.add_node("response_payload", response_payload_node)

        workflow.add_edge(START, "input_transcript")
        workflow.add_conditional_edges(
            "input_transcript",
            route_after_required_input,
            {"continue": "quick_safety_flag", "stop": END},
        )
        workflow.add_edge("quick_safety_flag", "semantic_extraction")
        workflow.add_edge("semantic_extraction", "schema_quote_validation")
        workflow.add_conditional_edges(
            "schema_quote_validation",
            route_after_schema_validation,
            {"continue": "hybrid_ir_match", "safety": "safety_guardrail_save", "stop": END},
        )
        workflow.add_edge("hybrid_ir_match", "session_validation_save")
        workflow.add_conditional_edges(
            "session_validation_save",
            route_after_save,
            {"continue": "onepaper_refresh", "stop": END},
        )
        workflow.add_conditional_edges(
            "safety_guardrail_save",
            route_after_save,
            {"continue": "onepaper_refresh", "stop": END},
        )
        workflow.add_edge("onepaper_refresh", "response_payload")
        workflow.add_edge("response_payload", END)
        _compiled_graph._graph = workflow.compile()
    return _compiled_graph._graph


def _trace(
    state: AnswerPipelineState,
    node: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "trace": _next_trace_entry(state, node, status, details or {}),
        "active_path": [*state.get("active_path", []), node],
    }


def _next_trace_entry(
    state: AnswerPipelineState,
    node: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trace = list(state.get("trace") or [])
    trace.append(
        {
            "node": node,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }
    )
    return trace


def _orchestration_snapshot(state: AnswerPipelineState, trace: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "graph": PIPELINE_GRAPH["name"],
        "version": PIPELINE_GRAPH["version"],
        "nodes": PIPELINE_GRAPH["nodes"],
        "edges": PIPELINE_GRAPH["edges"],
        "active_path": [entry["node"] for entry in trace],
        "question_type": state.get("question_type"),
        "trace": trace,
    }


def _response_errors(state: AnswerPipelineState) -> list[str]:
    if state.get("safety_only"):
        return ["semantic_extraction_failed_but_safety_saved"]
    validated = state.get("validated") or {}
    return validated.get("errors", [])


def _persist_final_trace(state: AnswerPipelineState, final_trace: list[dict[str, Any]]) -> None:
    """DynamoDB 문항 기록에 최종 LangGraph trace를 best-effort로 반영합니다.

    `validate_and_save`는 저장 노드 내부에서 호출되므로, 그 시점에는 아직
    `onepaper_refresh`와 `response_payload` 노드가 실행되지 않았습니다. 최종 trace는
    환자 문진 결과 자체가 아니라 설명 가능성 메타데이터이므로, 저장 실패가 문진 처리
    성공 여부를 바꾸지 않도록 조용히 무시합니다.
    """
    try:
        from sessions import get_session, update_session

        session_id = state.get("session_id")
        question_id = state.get("question_id")
        if not session_id or not question_id:
            return
        session = get_session(session_id)
        if not session:
            return

        orchestration = _orchestration_snapshot(state, final_trace)
        responses = dict(session.get("responses") or {})
        question_results = dict(session.get("question_results") or {})
        for collection in (responses, question_results):
            record = dict(collection.get(question_id) or {})
            if record:
                record["orchestration"] = orchestration
                record["pipeline_trace"] = final_trace
                collection[question_id] = record
        update_session(session_id, {"responses": responses, "question_results": question_results})
    except Exception:
        return
