#!/usr/bin/env python3
"""RAG 기반 사투리→표준어 의미 동등성 평가.

이 스크립트는 발표용 성능검증에서 필요한 질문 하나에 집중합니다.
"사투리/구어체 원문을 표준어로 바꿨을 때 의미가 같은가?"

흐름:
1. dialect_text 또는 text 입력
2. dialect_rag.retrieve_dialect_context()로 강원 방언팩 힌트 검색
3. Nova Lite가 표준어 문장 생성
4. Nova Lite judge가 원문과 변환문 의미 동등성 평가
5. 의미 동일률, 표준어 자연성, 새 사실 추가 방지율, 의미 누락 방지율 집계
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MODEL_ID = "apac.amazon.nova-lite-v1:0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = PROJECT_ROOT / "backend" / "serverless" / "src"
sys.path.insert(0, str(BACKEND_SRC))

try:
    from dialect_rag import retrieve_dialect_context  # type: ignore
    from llm import call_bedrock_json_with_meta  # type: ignore
except ModuleNotFoundError as exc:
    raise SystemExit(
        "backend/serverless/src 모듈을 불러오지 못했습니다. "
        "프로젝트 루트에서 실행하거나 의존성 설치 상태를 확인하세요. "
        f"누락 모듈: {exc.name}"
    ) from exc


def main() -> int:
    args = parse_args()
    rows = []
    cases = load_cases(args.input)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit(f"평가 case가 없습니다: {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for idx, case in enumerate(cases, start=1):
        row = evaluate_case(case, idx, args)
        rows.append(row)
        print(
            f"[{idx}/{len(cases)}] {row['case_id']} "
            f"success={row['semantic_success']} "
            f"same={row['same_meaning']} "
            f"std={row['standard_korean']} "
            f"added={row['added_fact']} "
            f"omitted={row['omitted_fact']} "
            f"hints={row['rag_hint_count']}"
        )

    summary = summarize(rows, args)
    write_json(args.output_dir / "dialect_semantic_summary.json", summary)
    write_jsonl(args.output_dir / "dialect_semantic_case_results.jsonl", rows)
    write_csv(args.output_dir / "dialect_semantic_case_results.csv", rows)
    write_csv(args.output_dir / "dialect_semantic_failed_cases.csv", [r for r in rows if r["failure_type"] != "ok"])

    print("\nRAG 기반 사투리→표준어 의미 평가 요약")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    print(f"\n결과 저장: {args.output_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG 기반 사투리→표준어 의미 동등성 평가")
    parser.add_argument("--input", type=Path, required=True, help="평가 JSONL 또는 JSON 배열/객체 파일")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/dialect_rag/reports/run_latest"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--model-id",
        default=os.environ.get("DIALECT_SEMANTIC_MODEL_ID") or os.environ.get("DIALECT_NORMALIZER_MODEL_ID") or DEFAULT_MODEL_ID,
    )
    parser.add_argument(
        "--judge-model-id",
        default=(
            os.environ.get("DIALECT_SEMANTIC_JUDGE_MODEL_ID")
            or os.environ.get("DIALECT_EVAL_JUDGE_MODEL_ID")
            or os.environ.get("DIALECT_NORMALIZER_MODEL_ID")
            or DEFAULT_MODEL_ID
        ),
    )
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("DIALECT_SEMANTIC_MAX_TOKENS", "700")))
    parser.add_argument("--judge-max-tokens", type=int, default=int(os.environ.get("DIALECT_SEMANTIC_JUDGE_MAX_TOKENS", "700")))
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    """JSON 배열, {data:[...]}, {cases:[...]}, JSONL 모두 읽는다.

    JSONL은 첫 줄이 `{`로 시작할 수 있으므로, 파일 전체를 무조건 json.loads 하면
    `JSONDecodeError: Extra data`가 난다. 먼저 전체 JSON 파싱을 시도하고 실패하면
    줄 단위 JSONL로 fallback한다.
    """
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []

    if text[0] in "[{":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = data.get("data") or data.get("cases") or []
            if not isinstance(data, list):
                raise ValueError("JSON 입력은 list 또는 {data:[...]} 형태여야 합니다.")
            return [item for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            # JSONL일 가능성이 높으므로 아래 줄 단위 파서로 이어간다.
            pass

    rows = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} JSONL 파싱 실패: {exc}") from exc
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def evaluate_case(case: dict[str, Any], idx: int, args: argparse.Namespace) -> dict[str, Any]:
    case_id = str(case.get("case_id") or f"case_{idx:03d}")
    original = normalize_ws(str(case.get("dialect_text") or case.get("text") or case.get("transcript") or ""))
    gold = normalize_ws(str(case.get("gold_standard_text") or case.get("standard_text") or ""))
    if not original:
        raise ValueError(f"{case_id}: dialect_text/text가 비어 있습니다.")

    rag_context = retrieve_dialect_context(original)
    normalized = normalize_with_rag(original, rag_context, args.model_id, args.max_tokens)
    predicted = normalize_ws(normalized.get("standardized_text") or original)
    judge = judge_meaning(original, gold, predicted, args.judge_model_id, args.judge_max_tokens)

    semantic_success = (
        judge.get("same_meaning") is True
        and judge.get("standard_korean") is True
        and judge.get("added_fact") is False
        and judge.get("omitted_fact") is False
    )

    return {
        "case_id": case_id,
        "dialect_type": case.get("dialect_type", ""),
        "original_text": original,
        "gold_standard_text": gold,
        "predicted_standard_text": predicted,
        "same_meaning": judge.get("same_meaning"),
        "standard_korean": judge.get("standard_korean"),
        "added_fact": judge.get("added_fact"),
        "omitted_fact": judge.get("omitted_fact"),
        "semantic_success": bool(semantic_success),
        "failure_type": classify_failure(judge, bool(semantic_success)),
        "rag_hint_count": len(rag_context.get("hints") or []),
        "rag_hints": summarize_hints(rag_context),
        "normalizer_reason": normalized.get("reason", ""),
        "judge_reason": judge.get("reason", ""),
        "normalizer_error": normalized.get("error", ""),
        "judge_error": judge.get("error", ""),
        "model_id": args.model_id,
        "judge_model_id": args.judge_model_id,
    }


def normalize_with_rag(text: str, rag_context: dict[str, Any], model_id: str, max_tokens: int) -> dict[str, str]:
    hints = rag_context.get("prompt_note") or ""
    prompt = f"""
너는 병원 문진 문장의 강원 사투리/구어체를 자연스러운 표준어로 바꾸는 도우미다.
환자가 말한 의미를 보존하고, 새로운 증상·약·시점·정도를 추가하지 마라.
부정 표현, 호전/악화, 현재 남아 있는 증상, 질문 의도를 그대로 유지하라.
아래 RAG 힌트는 방언 어휘 참고용이며, 원문에 없는 사실을 만들면 안 된다.

환자 원문:
{text}

RAG 힌트:
{hints}

JSON만 반환하라.
{{
  "standardized_text": "의미를 그대로 보존한 표준어 문장",
  "reason": "짧은 한국어 설명"
}}
""".strip()
    try:
        obj, _raw, _meta = call_bedrock_json_with_meta(prompt, model_id, max_tokens)
    except Exception as exc:
        return {"standardized_text": text, "reason": "", "error": f"normalizer_error:{exc.__class__.__name__}"}
    if not isinstance(obj, dict):
        return {"standardized_text": text, "reason": "", "error": "normalizer_output_not_object"}
    return {
        "standardized_text": normalize_ws(str(obj.get("standardized_text") or text)),
        "reason": str(obj.get("reason") or ""),
        "error": "",
    }


def judge_meaning(original: str, gold: str, predicted: str, model_id: str, max_tokens: int) -> dict[str, Any]:
    gold_block = f"정답 표준어 문장:\n{gold}\n" if gold else "정답 표준어 문장은 없다. 원문과 변환문만 비교하라.\n"
    prompt = f"""
너는 사투리 표준어 변환 결과를 평가한다.
평가 기준은 문진 의미 보존이다. 의학적 판단을 하지 말고 문장 의미만 비교하라.

same_meaning=true 조건:
- 증상, 부정 표현, 시작/지속/호전/악화, 정도, 복약 사실, 질문 의도가 유지됨
standard_korean=true 조건:
- 변환문이 자연스러운 표준어 문장임
added_fact=true 조건:
- 원문/정답에 없는 증상, 약, 시점, 정도, 확신, 질문이 추가됨
omitted_fact=true 조건:
- 원문/정답에 있던 증상, 부정, 시점, 정도, 복약 사실, 질문 의도가 빠짐

사투리/구어체 원문:
{original}

{gold_block}모델 표준어 변환문:
{predicted}

JSON만 반환하라.
{{
  "same_meaning": true 또는 false,
  "standard_korean": true 또는 false,
  "added_fact": true 또는 false,
  "omitted_fact": true 또는 false,
  "reason": "짧은 한국어 근거"
}}
""".strip()
    try:
        obj, _raw, _meta = call_bedrock_json_with_meta(prompt, model_id, max_tokens)
    except Exception as exc:
        return {
            "same_meaning": None,
            "standard_korean": None,
            "added_fact": None,
            "omitted_fact": None,
            "reason": "",
            "error": f"judge_error:{exc.__class__.__name__}",
        }
    if not isinstance(obj, dict):
        return {
            "same_meaning": None,
            "standard_korean": None,
            "added_fact": None,
            "omitted_fact": None,
            "reason": "",
            "error": "judge_output_not_object",
        }
    return {
        "same_meaning": coerce_bool(obj.get("same_meaning")),
        "standard_korean": coerce_bool(obj.get("standard_korean")),
        "added_fact": coerce_bool(obj.get("added_fact")),
        "omitted_fact": coerce_bool(obj.get("omitted_fact")),
        "reason": str(obj.get("reason") or ""),
        "error": "",
    }


def classify_failure(judge: dict[str, Any], success: bool) -> str:
    if judge.get("error"):
        return "judge_error"
    if success:
        return "ok"
    if judge.get("added_fact") is True:
        return "added_fact"
    if judge.get("omitted_fact") is True:
        return "omitted_fact"
    if judge.get("same_meaning") is False:
        return "meaning_mismatch"
    if judge.get("standard_korean") is False:
        return "not_standard_korean"
    return "unknown_failure"


def summarize(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    n = max(1, len(rows))
    judged = [row for row in rows if not row.get("judge_error")]
    jn = max(1, len(judged))
    return {
        "case_count": len(rows),
        "model_id": args.model_id,
        "judge_model_id": args.judge_model_id,
        "semantic_success_rate": round(sum(1 for r in judged if r.get("semantic_success")) / jn, 4),
        "same_meaning_rate": round(sum(1 for r in judged if r.get("same_meaning") is True) / jn, 4),
        "standard_korean_rate": round(sum(1 for r in judged if r.get("standard_korean") is True) / jn, 4),
        "no_added_fact_rate": round(sum(1 for r in judged if r.get("added_fact") is False) / jn, 4),
        "no_omitted_fact_rate": round(sum(1 for r in judged if r.get("omitted_fact") is False) / jn, 4),
        "avg_rag_hint_count": round(sum(int(r.get("rag_hint_count") or 0) for r in rows) / n, 3),
        "failure_type_counts": count_by(rows, "failure_type"),
    }


def summarize_hints(context: dict[str, Any]) -> list[dict[str, str]]:
    hints = []
    for item in (context.get("hints") or [])[:5]:
        hints.append({
            "dialect": str(item.get("dialect") or ""),
            "standard": str(item.get("standard") or ""),
            "match_type": str(item.get("match_type") or ""),
        })
    return hints


def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "예", "맞음"}:
            return True
        if lowered in {"false", "no", "0", "아니오", "아님"}:
            return False
    return None


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id", "dialect_type", "semantic_success", "same_meaning", "standard_korean",
        "added_fact", "omitted_fact", "failure_type", "rag_hint_count",
        "original_text", "gold_standard_text", "predicted_standard_text",
        "normalizer_reason", "judge_reason", "normalizer_error", "judge_error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


if __name__ == "__main__":
    raise SystemExit(main())
