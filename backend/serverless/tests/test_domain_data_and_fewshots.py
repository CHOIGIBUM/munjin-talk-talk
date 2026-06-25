"""도메인별 IR 데이터 경로와 few-shot 로더 계약 테스트."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_fewshot_loader_reads_domain_managed_examples():
    from fewshots import load_fewshot_examples, render_fewshot_block  # noqa: E402

    examples = load_fewshot_examples("extraction", "respiratory")
    block = render_fewshot_block("extraction", "respiratory", limit=1)

    assert examples
    assert "어제부터 목이 칼칼하고 코가 맥혀요." in block
    assert "Expected JSON:" in block


def test_fewshot_selection_prefers_matching_question_type():
    from fewshots import render_fewshot_block  # noqa: E402

    block = render_fewshot_block("extraction", "respiratory", limit=1, question_type="patient_questions")

    assert "patient has no agenda in Q4" in block
    assert "따로 궁금한 건 없어요." in block


def test_data_source_prefers_domain_specific_ir_files(tmp_path, monkeypatch):
    import data_sources  # noqa: E402

    source_dir = tmp_path / "ir_sources" / "respiratory"
    source_dir.mkdir(parents=True)
    domain_file = source_dir / "diseases_cleaned.json"
    domain_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(data_sources, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_sources, "IR_SOURCE_DIR", tmp_path / "ir_sources")
    monkeypatch.delenv("DISEASES_PATH", raising=False)

    assert data_sources.resolve_ir_source_path("diseases_cleaned.json", "DISEASES_PATH", "respiratory") == domain_file


def test_data_source_keeps_legacy_fallback_when_domain_file_missing(tmp_path, monkeypatch):
    import data_sources  # noqa: E402

    monkeypatch.setattr(data_sources, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_sources, "IR_SOURCE_DIR", tmp_path / "ir_sources")

    assert data_sources.resolve_ir_source_path("symptom_index.json", "", "respiratory") == tmp_path / "symptom_index.json"
