from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def install_review_stubs():
    for name in ["settings", "llm"]:
        sys.modules.pop(name, None)

    settings = types.ModuleType("settings")
    settings.REVIEWER_MODEL_ID = "apac.amazon.nova-pro-v1:0"
    settings.REVIEW_MAX_TOKENS = 900
    settings.REVIEW_RETRY_ATTEMPTS = 1
    sys.modules["settings"] = settings

    llm = types.ModuleType("llm")

    def fail_review(*_args, **_kwargs):
        raise RuntimeError("bedrock unavailable")

    llm.call_bedrock_json_with_meta = fail_review
    sys.modules["llm"] = llm


def test_review_fallback_keeps_doctor_checklist_non_empty():
    install_review_stubs()
    sys.modules.pop("onepager_review", None)
    from onepager_review import apply_bedrock_onepager_review  # noqa: E402

    onepager = {
        "symptom_slots": [
            {"name": "흉통", "source_quote": "가슴이 답답함", "status": "있음"},
        ],
        "clinical_clues": [
            {"summary": "어제부터 시작", "action_hint": "시작 시점과 악화 여부 확인"},
        ],
        "agenda": [
            {"summary": "약을 같이 먹어도 되는지 문의", "original_quote": "약들 같이 다 먹어도 되지?"},
        ],
        "safety_flags": [
            {"label": "흉통", "category": "chest_pain", "matched_pattern": "가슴이 답답함"},
        ],
        "review_items": [],
        "transfer_text": "",
    }

    reviewed = apply_bedrock_onepager_review({"visit_type": "initial", "patient": {}, "responses": {}}, onepager)

    assert reviewed["review_items"]
    assert reviewed["review_item_generation"]["method"] == "rule_based_fallback"
    assert any(item.startswith("[우선]") for item in reviewed["review_items"])
    assert any("흉통" in item for item in reviewed["review_items"])


def test_transfer_text_filter_rejects_patient_facing_prose():
    install_review_stubs()
    sys.modules.pop("onepager_review", None)
    from onepager_review import is_transfer_text_safe  # noqa: E402

    onepager = {
        "patient_summary": {"age_text": "80세", "sex": "남성"},
        "symptom_slots": [{"name": "천명음", "source_quote": "쌕쌕 나와", "normalized_text": "천명음"}],
        "clinical_clues": [],
        "agenda": [],
        "safety_flags": [],
    }

    narrative = "S: 80세 남성 초진. 환자는 현재 가슴이 답답하다고 언급했습니다 | O: 문진 기반 객관소견 없음"
    chart_like = "S) 80세 남성 초진 / CC: 천명음 / 확인: 증상 지속시간/중증도"

    assert is_transfer_text_safe(narrative, onepager) is False
    assert is_transfer_text_safe(chart_like, onepager) is True
