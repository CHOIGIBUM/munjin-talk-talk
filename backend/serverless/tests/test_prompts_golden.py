"""프롬프트 회귀 방지 테스트.

기본 문항의 LLM 프롬프트는 의료 품질과 테스트 재현성에 직접 영향을 줍니다.
이 테스트는 커밋 9951f27의 기준 출력과 현재 출력이 완전히 같은지 비교합니다.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 프롬프트 골든 테스트는 AWS client 초기화가 아니라 문자열 계약을 검증합니다.
# 로컬 테스트에서 boto3 credential/네트워크 상태에 흔들리지 않도록 필요한 값만 고정합니다.
settings = types.ModuleType("settings")
settings.LIGHT_MODEL_ID = "apac.amazon.nova-lite-v1:0"
settings.STRONG_MODEL_ID = "apac.amazon.nova-pro-v1:0"
settings.REVIEWER_MODEL_ID = "apac.amazon.nova-pro-v1:0"
settings.REVIEW_MAX_TOKENS = 900
settings.REVIEW_RETRY_ATTEMPTS = 2
sys.modules["settings"] = settings

llm = types.ModuleType("llm")
llm.call_bedrock_json_with_meta = lambda *args, **kwargs: ({}, "", {})
sys.modules["llm"] = llm

from extraction_prompts import (  # noqa: E402
    build_extraction_prompt,
    build_extraction_repair_note,
    select_extraction_model,
)
from onepager_review import build_onepager_review_prompt  # noqa: E402


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "prompts_golden.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_extraction_prompts_match_golden():
    """8개 기본 문항의 모델 선택과 프롬프트가 골든과 동일해야 합니다."""
    data = load_fixture()
    for case in data["cases"]:
        current_model = select_extraction_model(case["visit"], case["qid"], case["qtype"])
        current_prompt = build_extraction_prompt(
            case["visit"],
            case["qid"],
            case["qtype"],
            "어제부터 기침이 나요",
            repair_note="",
            rag_context_note="RAGNOTE_PLACEHOLDER",
        )
        assert current_model == case["model"]
        assert current_prompt == case["prompt"]


def test_repair_note_matches_golden():
    """LLM repair prompt도 검증 실패 원인 전달 방식이 흔들리면 안 됩니다."""
    data = load_fixture()
    current = build_extraction_repair_note(
        [{"field": "spans.0.slot_ref", "type": "literal_error", "message": "bad"}],
        "어제부터 기침이 나요",
    )
    assert current == data["repair_note"]


def test_known_question_uses_server_text_before_client_override():
    """기본 Q1-Q4는 클라이언트가 보낸 질문 문구로 prompt를 오염시키지 않습니다."""
    prompt = build_extraction_prompt(
        "initial",
        "Q1",
        "chief_complaint",
        "기침이 나요",
        question_text_override="조작된 질문",
    )
    assert "Question asked: 어디가 불편하셔서 오셨어요?" in prompt
    assert "조작된" not in prompt


def test_onepager_review_prompt_matches_golden():
    """의료진 체크리스트 생성 prompt가 기준 문구와 동일해야 합니다."""
    data = load_fixture()
    session = {
        "session_id": "s_test",
        "visit_type": "initial",
        "patient": {
            "name": "김*수",
            "age_band": "70대",
            "gender": "남",
            "department": "호흡기내과",
        },
    }
    onepager = {
        "patient_summary": "70대 남성",
        "symptom_slots": [{"name": "기침", "source_quote": "기침이 나요", "status": "있음"}],
        "clinical_clues": [],
        "agenda": [],
        "safety_flags": [],
        "raw_answers": {"Q1": "어제부터 기침이 나요"},
    }
    assert build_onepager_review_prompt(session, onepager) == data["review_prompt"]
