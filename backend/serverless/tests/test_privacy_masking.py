"""개인정보 표시명 마스킹 회귀 테스트."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils import mask_name  # noqa: E402
from privacy import sanitize_reception_patient  # noqa: E402


def test_mask_name_handles_two_three_and_four_character_names():
    """이름 길이가 달라도 첫 글자 외의 직접 노출을 최소화합니다."""
    assert mask_name("공이") == "공*"
    assert mask_name("홍길동") == "홍*동"
    assert mask_name("최찬범길") == "최**길"


def test_mask_name_keeps_existing_masked_display_names_stable():
    """응답 직전 재마스킹을 해도 이미 마스킹된 표시명은 깨지지 않습니다."""
    assert mask_name("공*") == "공*"
    assert mask_name("홍*동") == "홍*동"
    assert mask_name("최**길") == "최**길"


def test_mask_name_removes_inner_spaces_before_masking():
    """접수 입력에 공백이 들어와도 동일한 마스킹 정책을 적용합니다."""
    assert mask_name("홍 길동") == "홍*동"
    assert mask_name(" 남궁 민수 ") == "남**수"


def test_reception_patient_stores_masked_display_name_only():
    """접수 저장 payload에는 실명 대신 길이별 마스킹 표시명만 남깁니다."""
    patient = sanitize_reception_patient({"full_name": "공이", "birth_date": "1950-01-01"})

    assert patient["name"] == "공*"
    assert "full_name" not in patient
    assert "birth_date" not in patient
