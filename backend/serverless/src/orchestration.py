"""Question processing orchestration.

프론트엔드가 확인된 환자 발화 1개를 보내면 이 모듈이 LangGraph 기반
파이프라인을 실행합니다. 실제 노드 정의는 `pipeline_graph.py`에 있고,
이 파일은 기존 handler/import 계약을 유지하는 얇은 진입점 역할만 합니다.
"""

from pipeline_graph import PIPELINE_GRAPH, run_answer_pipeline


def process_answer(body):
    """환자 답변 1개를 LangGraph 파이프라인으로 처리합니다."""
    return run_answer_pipeline(body)
