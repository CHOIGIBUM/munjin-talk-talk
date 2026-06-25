#!/usr/bin/env python3
"""Validate MunjinTalkTalk IR evaluation datasets.

The evaluator accepts compact cases that contain patient text plus gold symptom
labels. This helper checks that those labels exist in the current symptom index
and that visit/question combinations are valid for the configured question set.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "evaluation" / "ir" / "data" / "eval_cases.json"
SYMPTOM_INDEX_PATH = PROJECT_ROOT / "backend" / "serverless" / "src" / "data" / "symptom_index.json"
QUESTION_SET_PATH = PROJECT_ROOT / "backend" / "serverless" / "src" / "data" / "question_sets" / "default.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = resolve_project_path(args.input)
    cases = load_cases(input_path)
    symptom_names = load_symptom_names(resolve_project_path(args.symptom_index))
    question_map = load_question_map(resolve_project_path(args.question_set))

    errors, warnings, summary = validate_cases(cases, symptom_names, question_map)
    summary["input"] = str(input_path)
    summary["symptom_index"] = str(resolve_project_path(args.symptom_index))
    summary["question_set"] = str(resolve_project_path(args.question_set))

    print_summary(summary, errors, warnings)
    if args.summary_output:
        output_path = resolve_project_path(args.summary_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "errors": errors,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nsummary saved: {output_path}")

    return 1 if errors else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate IR evaluation dataset labels and question metadata.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Evaluation JSON/JSONL input path")
    parser.add_argument("--symptom-index", type=Path, default=SYMPTOM_INDEX_PATH, help="symptom_index.json path")
    parser.add_argument("--question-set", type=Path, default=QUESTION_SET_PATH, help="question set JSON path")
    parser.add_argument("--summary-output", type=Path, default=None, help="Optional JSON summary output path")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [row for row in data["data"] if isinstance(row, dict)]
        if data is not None:
            raise ValueError(f"Unsupported JSON shape: {path}")

    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no} must be a JSON object")
        rows.append(row)
    return rows


def load_symptom_names(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(key) for key in data.keys()}
    if isinstance(data, list):
        names = set()
        for item in data:
            if isinstance(item, dict):
                value = item.get("display_name") or item.get("name") or item.get("canonical_name")
                if value:
                    names.add(str(value))
        return names
    return set()


def load_question_map(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    visits = data.get("visits") if isinstance(data, dict) else {}
    result: dict[str, dict[str, str]] = {}
    for visit_type, questions in (visits or {}).items():
        if not isinstance(questions, list):
            continue
        result[str(visit_type)] = {
            str(question.get("id")): str(question.get("question_type") or "")
            for question in questions
            if isinstance(question, dict) and question.get("id")
        }
    return result


def validate_cases(
    cases: list[dict[str, Any]],
    symptom_names: set[str],
    question_map: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    case_ids: Counter[str] = Counter()
    visits: Counter[str] = Counter()
    questions: Counter[str] = Counter()
    dialects: Counter[str] = Counter()
    gold_symptoms: Counter[str] = Counter()
    negative_symptoms: Counter[str] = Counter()
    question_types: Counter[str] = Counter()
    multi_gold_cases = 0

    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or f"<row_{index}>")
        case_ids[case_id] += 1
        visit_type = normalize_visit_type(case.get("visit_type"))
        question_id = str(case.get("question_id") or "")
        dialect_type = str(case.get("dialect_type") or "")
        text = str(case.get("text") or case.get("transcript") or case.get("raw_text") or "")
        gold = [str(item) for item in (case.get("gold_symptoms") or [])]
        negative = [str(item) for item in (case.get("negative_symptoms") or [])]

        visits[visit_label(visit_type)] += 1
        questions[question_id or "<missing>"] += 1
        dialects[dialect_type or "<missing>"] += 1
        if len(gold) > 1:
            multi_gold_cases += 1
        gold_symptoms.update(gold)
        negative_symptoms.update(negative)

        if not case.get("case_id"):
            errors.append(error(case_id, "missing_case_id", "case_id is required"))
        if case_ids[case_id] > 1:
            errors.append(error(case_id, "duplicate_case_id", f"duplicate case_id: {case_id}"))
        if not text.strip():
            errors.append(error(case_id, "missing_text", "text/transcript is required"))
        if not gold:
            warnings.append(error(case_id, "empty_gold_symptoms", "gold_symptoms is empty"))

        visit_questions = question_map.get(visit_type) or {}
        question_type = visit_questions.get(question_id)
        if not question_type:
            errors.append(
                error(
                    case_id,
                    "invalid_question_id",
                    f"{visit_label(visit_type)} {question_id or '<missing>'} is not in question set",
                )
            )
        else:
            question_types[question_type] += 1

        for field_name, values in (("gold_symptoms", gold), ("negative_symptoms", negative)):
            for symptom in values:
                if symptom not in symptom_names:
                    errors.append(
                        error(
                            case_id,
                            "unknown_symptom",
                            f"{field_name} contains unknown symptom: {symptom}",
                        )
                    )

    summary = {
        "case_count": len(cases),
        "visit_counts": dict(sorted(visits.items())),
        "question_counts": dict(sorted(questions.items())),
        "question_type_counts": dict(sorted(question_types.items())),
        "dialect_counts": dict(sorted(dialects.items())),
        "multi_gold_case_count": multi_gold_cases,
        "unique_gold_symptom_count": len(gold_symptoms),
        "unique_negative_symptom_count": len(negative_symptoms),
        "top_gold_symptoms": dict(gold_symptoms.most_common(20)),
        "top_negative_symptoms": dict(negative_symptoms.most_common(20)),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return errors, warnings, summary


def normalize_visit_type(value: Any) -> str:
    return "followup" if value in ("followup", "재진") else "initial"


def visit_label(value: str) -> str:
    return "재진" if value == "followup" else "초진"


def error(case_id: str, code: str, message: str) -> dict[str, Any]:
    return {"case_id": case_id, "code": code, "message": message}


def print_summary(summary: dict[str, Any], errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    print("Evaluation dataset validation")
    print(f"- cases: {summary['case_count']}")
    print(f"- visits: {summary['visit_counts']}")
    print(f"- questions: {summary['question_counts']}")
    print(f"- question_types: {summary['question_type_counts']}")
    print(f"- dialects: {summary['dialect_counts']}")
    print(f"- unique_gold_symptoms: {summary['unique_gold_symptom_count']}")
    print(f"- errors: {len(errors)}")
    print(f"- warnings: {len(warnings)}")
    if errors:
        print("\nErrors")
        for item in errors[:50]:
            print(f"- {item['case_id']} [{item['code']}] {item['message']}")
        if len(errors) > 50:
            print(f"- ... {len(errors) - 50} more")
    if warnings:
        print("\nWarnings")
        for item in warnings[:20]:
            print(f"- {item['case_id']} [{item['code']}] {item['message']}")
        if len(warnings) > 20:
            print(f"- ... {len(warnings) - 20} more")


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
