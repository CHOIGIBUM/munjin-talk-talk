"""Offline IR/RAG evaluation for the clean train_100 dataset.

This does not call Bedrock. It evaluates the deterministic runtime candidate
search layer that feeds the LLM and the IR linker.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "serverless" / "src"
sys.path.insert(0, str(BACKEND_SRC))

from rag_context import retrieve_alias_hints, retrieve_symptom_references  # noqa: E402
from retrieval_documents import get_ir_index  # noqa: E402


CASES_PATH = ROOT / "evaluation" / "generated" / "train_100" / "cases.jsonl"
RESULTS_PATH = ROOT / "evaluation" / "train_100_evaluation" / "offline_ir_results.json"
REPORT_PATH = ROOT / "evaluation" / "train_100_evaluation" / "case_analysis.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ranked_bm25_names(query: str) -> list[dict[str, Any]]:
    docs, bm25 = get_ir_index()
    scores = bm25.scores(query)
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    rows = []
    for idx, score in ranked:
        if score <= 0:
            continue
        doc = docs[idx]
        rows.append(
            {
                "rank": len(rows) + 1,
                "name": doc.get("display_name"),
                "slot_id": doc.get("symptom_id"),
                "bm25_score": round(float(score), 4),
                "source": doc.get("source"),
            }
        )
    return rows


def ranked_rag_names(query: str) -> list[dict[str, Any]]:
    refs = retrieve_symptom_references(query, top_k=10)
    return [
        {
            "rank": idx,
            "name": item.get("display_name"),
            "slot_id": item.get("symptom_id"),
            "bm25_score": item.get("bm25_score"),
            "rank_score": item.get("rank_score"),
            "alias_match": item.get("alias_match") or {},
            "source": "runtime_rag_context",
        }
        for idx, item in enumerate(refs, start=1)
    ]


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    text = case["text"]
    gold = set(case.get("gold_symptoms") or [])
    negative = set(case.get("negative_symptoms") or [])
    alias_hints = retrieve_alias_hints(text)
    alias_active_names = [
        item.get("canonical_hint")
        for item in alias_hints
        if item.get("canonical_hint") and item.get("polarity") != "inactive_or_negated"
    ]
    alias_inactive_names = [
        item.get("canonical_hint")
        for item in alias_hints
        if item.get("canonical_hint") and item.get("polarity") == "inactive_or_negated"
    ]
    ranked = ranked_bm25_names(text)
    rag_ranked = ranked_rag_names(text)

    def top_names(rows: list[dict[str, Any]], k: int) -> set[str]:
        return {row["name"] for row in rows[:k]}

    top_by_k = {str(k): top_names(ranked, k) for k in (1, 3, 5, 10)}
    rag_top_by_k = {str(k): top_names(rag_ranked, k) for k in (1, 3, 5, 10)}
    gold_hits = {str(k): sorted(gold & names) for k, names in top_by_k.items()}
    gold_misses = {str(k): sorted(gold - names) for k, names in top_by_k.items()}
    negative_hits = {str(k): sorted(negative & names) for k, names in top_by_k.items()}
    rag_gold_hits = {str(k): sorted(gold & names) for k, names in rag_top_by_k.items()}
    rag_gold_misses = {str(k): sorted(gold - names) for k, names in rag_top_by_k.items()}
    rag_negative_hits = {str(k): sorted(negative & names) for k, names in rag_top_by_k.items()}
    alias_gold_hits = sorted(gold & set(alias_active_names))
    alias_gold_misses = sorted(gold - set(alias_active_names))
    alias_negative_hits = sorted(negative & set(alias_active_names))
    alias_inactive_negative_hits = sorted(negative & set(alias_inactive_names))

    return {
        "case_id": case["case_id"],
        "visit_type": case["visit_type"],
        "question_id": case["question_id"],
        "question_type": case["question_type"],
        "dialect_type": case["dialect_type"],
        "symptom_group": case["symptom_group"],
        "status_pattern": case["status_pattern"],
        "difficulty": case["difficulty"],
        "text": text,
        "gold_symptoms": sorted(gold),
        "negative_symptoms": sorted(negative),
        "alias_hints": alias_hints,
        "alias_gold_hits": alias_gold_hits,
        "alias_gold_misses": alias_gold_misses,
        "alias_negative_hits": alias_negative_hits,
        "alias_inactive_negative_hits": alias_inactive_negative_hits,
        "bm25_top10": ranked[:10],
        "rag_top10": rag_ranked[:10],
        "gold_hits": gold_hits,
        "gold_misses": gold_misses,
        "negative_hits": negative_hits,
        "rag_gold_hits": rag_gold_hits,
        "rag_gold_misses": rag_gold_misses,
        "rag_negative_hits": rag_negative_hits,
        "top1_is_gold": bool(ranked and ranked[0]["name"] in gold),
        "all_gold_in_top5": not gold_misses["5"],
        "any_gold_in_top5": bool(gold_hits["5"]),
        "negative_in_top5": bool(negative_hits["5"]),
        "rag_top1_is_gold": bool(rag_ranked and rag_ranked[0]["name"] in gold),
        "rag_all_gold_in_top5": not rag_gold_misses["5"],
        "rag_any_gold_in_top5": bool(rag_gold_hits["5"]),
        "rag_negative_in_top5": bool(rag_negative_hits["5"]),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_gold = sum(len(row["gold_symptoms"]) for row in records)
    total_negative = sum(len(row["negative_symptoms"]) for row in records)

    def micro_recall(k: str) -> float:
        return safe_div(sum(len(row["gold_hits"][k]) for row in records), total_gold)

    def rag_micro_recall(k: str) -> float:
        return safe_div(sum(len(row["rag_gold_hits"][k]) for row in records), total_gold)

    def case_all(k: str) -> float:
        return safe_div(sum(not row["gold_misses"][k] for row in records), len(records))

    def rag_case_all(k: str) -> float:
        return safe_div(sum(not row["rag_gold_misses"][k] for row in records), len(records))

    def case_any(k: str) -> float:
        return safe_div(sum(bool(row["gold_hits"][k]) for row in records), len(records))

    def rag_case_any(k: str) -> float:
        return safe_div(sum(bool(row["rag_gold_hits"][k]) for row in records), len(records))

    summary = {
        "dataset": "train_100",
        "evaluation_type": "offline_ir_rag_training_sanity",
        "is_held_out": False,
        "case_count": len(records),
        "total_gold_labels": total_gold,
        "total_negative_labels": total_negative,
        "alias_gold_micro_recall": safe_div(sum(len(row["alias_gold_hits"]) for row in records), total_gold),
        "alias_negative_leak_case_rate": safe_div(sum(bool(row["alias_negative_hits"]) for row in records), len(records)),
        "alias_inactive_negative_marker_case_rate": safe_div(
            sum(bool(row["alias_inactive_negative_hits"]) for row in records),
            len(records),
        ),
        "bm25_micro_recall": {f"recall@{k}": micro_recall(k) for k in ("1", "3", "5", "10")},
        "bm25_case_all_hit": {f"all_hit@{k}": case_all(k) for k in ("1", "3", "5", "10")},
        "bm25_case_any_hit": {f"any_hit@{k}": case_any(k) for k in ("1", "3", "5", "10")},
        "bm25_top1_case_accuracy": safe_div(sum(row["top1_is_gold"] for row in records), len(records)),
        "bm25_negative_leak_case_rate": {
            f"negative_in_top{k}": safe_div(sum(bool(row["negative_hits"][k]) for row in records), len(records))
            for k in ("1", "3", "5", "10")
        },
        "rag_micro_recall": {f"recall@{k}": rag_micro_recall(k) for k in ("1", "3", "5", "10")},
        "rag_case_all_hit": {f"all_hit@{k}": rag_case_all(k) for k in ("1", "3", "5", "10")},
        "rag_case_any_hit": {f"any_hit@{k}": rag_case_any(k) for k in ("1", "3", "5", "10")},
        "rag_top1_case_accuracy": safe_div(sum(row["rag_top1_is_gold"] for row in records), len(records)),
        "rag_negative_leak_case_rate": {
            f"negative_in_top{k}": safe_div(sum(bool(row["rag_negative_hits"][k]) for row in records), len(records))
            for k in ("1", "3", "5", "10")
        },
        "by_dialect": summarize_group(records, "dialect_type"),
        "by_question": summarize_group(records, "question_id"),
        "by_symptom_group": summarize_group(records, "symptom_group"),
        "failure_counts": {
            "alias_miss_cases": sum(bool(row["alias_gold_misses"]) for row in records),
            "bm25_top5_miss_cases": sum(bool(row["gold_misses"]["5"]) for row in records),
            "bm25_top5_negative_leak_cases": sum(bool(row["negative_hits"]["5"]) for row in records),
            "top1_not_gold_cases": sum(not row["top1_is_gold"] for row in records),
            "rag_top5_miss_cases": sum(bool(row["rag_gold_misses"]["5"]) for row in records),
            "rag_top5_negative_leak_cases": sum(bool(row["rag_negative_hits"]["5"]) for row in records),
            "rag_top1_not_gold_cases": sum(not row["rag_top1_is_gold"] for row in records),
        },
    }
    return summary


def summarize_group(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    out = {}
    for value in sorted({row[field] for row in records}):
        subset = [row for row in records if row[field] == value]
        gold_total = sum(len(row["gold_symptoms"]) for row in subset)
        out[value] = {
            "cases": len(subset),
            "gold_labels": gold_total,
            "alias_recall": safe_div(sum(len(row["alias_gold_hits"]) for row in subset), gold_total),
            "bm25_recall@5": safe_div(sum(len(row["gold_hits"]["5"]) for row in subset), gold_total),
            "rag_recall@5": safe_div(sum(len(row["rag_gold_hits"]["5"]) for row in subset), gold_total),
            "all_hit@5": safe_div(sum(not row["gold_misses"]["5"] for row in subset), len(subset)),
            "rag_all_hit@5": safe_div(sum(not row["rag_gold_misses"]["5"] for row in subset), len(subset)),
            "negative_in_top5_rate": safe_div(sum(bool(row["negative_hits"]["5"]) for row in subset), len(subset)),
            "rag_negative_in_top5_rate": safe_div(sum(bool(row["rag_negative_hits"]["5"]) for row in subset), len(subset)),
        }
    return out


def safe_div(a: float, b: float) -> float:
    return round(float(a) / float(b), 4) if b else 0.0


def write_results(summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps({"summary": summary, "cases": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def make_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# Train 100 Offline IR/RAG Evaluation",
        "",
        "이 평가는 held-out 성능 평가가 아니라, `train_100`으로 재구축한 런타임 artifact가 같은 train set을 후보 검색 단계에서 얼마나 덮는지 보는 sanity check입니다.",
        "Bedrock/LLM은 호출하지 않았고, 실제 런타임의 alias hint와 BM25 symptom index를 사용했습니다.",
        "",
        "## Summary",
        "",
        f"- cases: {summary['case_count']}",
        f"- total gold labels: {summary['total_gold_labels']}",
        f"- alias gold micro recall: {pct(summary['alias_gold_micro_recall'])}",
        f"- active alias negative leak case rate: {pct(summary['alias_negative_leak_case_rate'])}",
        f"- inactive alias negative marker case rate: {pct(summary['alias_inactive_negative_marker_case_rate'])}",
        f"- raw BM25 recall@1 / @3 / @5 / @10: {pct(summary['bm25_micro_recall']['recall@1'])} / {pct(summary['bm25_micro_recall']['recall@3'])} / {pct(summary['bm25_micro_recall']['recall@5'])} / {pct(summary['bm25_micro_recall']['recall@10'])}",
        f"- runtime RAG recall@1 / @3 / @5 / @10: {pct(summary['rag_micro_recall']['recall@1'])} / {pct(summary['rag_micro_recall']['recall@3'])} / {pct(summary['rag_micro_recall']['recall@5'])} / {pct(summary['rag_micro_recall']['recall@10'])}",
        f"- raw BM25 all-hit@5: {pct(summary['bm25_case_all_hit']['all_hit@5'])}",
        f"- runtime RAG all-hit@5: {pct(summary['rag_case_all_hit']['all_hit@5'])}",
        f"- raw BM25 top1 case accuracy: {pct(summary['bm25_top1_case_accuracy'])}",
        f"- runtime RAG top1 case accuracy: {pct(summary['rag_top1_case_accuracy'])}",
        f"- raw BM25 negative-in-top5 case rate: {pct(summary['bm25_negative_leak_case_rate']['negative_in_top5'])}",
        f"- runtime RAG negative-in-top5 case rate: {pct(summary['rag_negative_leak_case_rate']['negative_in_top5'])}",
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(interpret(summary))
    lines.extend(["", "## By Dialect", ""])
    lines.extend(group_table(summary["by_dialect"]))
    lines.extend(["", "## By Question", ""])
    lines.extend(group_table(summary["by_question"]))
    lines.extend(["", "## Main Failure Buckets", ""])
    for key, value in summary["failure_counts"].items():
        lines.append(f"- {key}: {value}")

    top5_misses = [row for row in records if row["rag_gold_misses"]["5"]]
    negative_leaks = [row for row in records if row["rag_negative_hits"]["5"]]
    alias_misses = [row for row in records if row["alias_gold_misses"]]
    top1_not_gold = [row for row in records if not row["rag_top1_is_gold"]]

    lines.extend(["", "## Runtime RAG Top5 Gold Miss Cases", ""])
    lines.extend(case_lines(top5_misses[:30], include_misses=True, ranking_key="rag_top10"))
    lines.extend(["", "## Runtime RAG Negative Leakage Cases", ""])
    lines.extend(case_lines(negative_leaks[:30], include_negative=True, ranking_key="rag_top10"))
    lines.extend(["", "## Alias Miss Samples", ""])
    lines.extend(case_lines(alias_misses[:30], include_alias=True, ranking_key="rag_top10"))
    lines.extend(["", "## Runtime RAG Top1 Not Gold Samples", ""])
    lines.extend(case_lines(top1_not_gold[:30], include_misses=False, ranking_key="rag_top10"))
    return "\n".join(lines) + "\n"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def group_table(group_summary: dict[str, Any]) -> list[str]:
    lines = [
        "| group | cases | gold labels | alias recall | BM25 recall@5 | RAG recall@5 | BM25 all-hit@5 | RAG all-hit@5 | BM25 neg@5 | RAG neg@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group, item in group_summary.items():
        lines.append(
            f"| {group} | {item['cases']} | {item['gold_labels']} | {pct(item['alias_recall'])} | "
            f"{pct(item['bm25_recall@5'])} | {pct(item['rag_recall@5'])} | "
            f"{pct(item['all_hit@5'])} | {pct(item['rag_all_hit@5'])} | "
            f"{pct(item['negative_in_top5_rate'])} | {pct(item['rag_negative_in_top5_rate'])} |"
        )
    return lines


def interpret(summary: dict[str, Any]) -> list[str]:
    lines = []
    if summary["rag_micro_recall"]["recall@5"] >= 0.95:
        lines.append("- Runtime RAG 후보 검색은 train set 내부에서는 대부분의 gold symptom을 top5 안에 올립니다.")
    else:
        lines.append("- Runtime RAG 후보 검색이 train set 내부에서도 gold symptom을 충분히 올리지 못합니다.")
    if summary["alias_gold_micro_recall"] < summary["rag_micro_recall"]["recall@5"]:
        lines.append("- alias hint는 BM25보다 보수적으로 작동합니다. 모든 gold를 직접 alias로 잡는 구조는 아니며, RAG 후보 보조 역할에 가깝습니다.")
    if summary["alias_inactive_negative_marker_case_rate"]:
        lines.append("- inactive alias marker는 부정/호전 문맥을 prompt hint로 남기되, runtime RAG reference 후보에서는 제외합니다.")
    if summary["rag_negative_leak_case_rate"]["negative_in_top5"] > 0.2:
        lines.append("- 부정된 증상도 후보에는 아직 일부 올라옵니다. 최종 판정은 LLM span type/status와 IR gate가 막아야 합니다.")
    lines.append("- 이 결과는 학습 데이터 자기검사라 일반화 성능으로 보고하면 안 됩니다. 다음 단계는 별도 test set으로 같은 산식을 반복하는 것입니다.")
    return lines


def case_lines(
    records: list[dict[str, Any]],
    *,
    include_misses: bool = False,
    include_negative: bool = False,
    include_alias: bool = False,
    ranking_key: str = "bm25_top10",
) -> list[str]:
    if not records:
        return ["- none"]
    lines = []
    for row in records:
        top5 = ", ".join(item["name"] for item in row[ranking_key][:5])
        line = f"- `{row['case_id']}` {row['question_id']} {row['dialect_type']} | text: {row['text']} | gold: {', '.join(row['gold_symptoms'])} | top5: {top5}"
        if include_misses:
            misses = row["rag_gold_misses"]["5"] if ranking_key == "rag_top10" else row["gold_misses"]["5"]
            line += f" | missed@5: {', '.join(misses)}"
        if include_negative:
            negative_hits = row["rag_negative_hits"]["5"] if ranking_key == "rag_top10" else row["negative_hits"]["5"]
            line += f" | negative: {', '.join(row['negative_symptoms'])} | negative@5: {', '.join(negative_hits)}"
        if include_alias:
            line += f" | alias_miss: {', '.join(row['alias_gold_misses'])}"
        lines.append(line)
    return lines


def main() -> None:
    cases = read_jsonl(CASES_PATH)
    records = [evaluate_case(case) for case in cases]
    summary = summarize(records)
    write_results(summary, records)
    REPORT_PATH.write_text(make_report(summary, records), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {RESULTS_PATH.relative_to(ROOT)}")
    print(f"wrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
