# Baseline 2026-06-26

문진톡톡 현재 구조 기준 합성 평가 데이터 100건 실행 결과입니다.

## Dataset

- 입력: `evaluation/ir/data/eval_cases.json`
- 총 100건
- 초진 60건, 재진 40건
- 표준어 50건, 사투리 50건
- Q1 81건, Q3 19건
- gold 표준 증상 47종
- validator 오류 0건

## Fast IR Baseline

문장 전체를 span으로 간주하고 LLM linker 없이 IR 후보군만 평가했습니다.

| Variant | candidate_recall@3 | candidate_recall@5 | candidate_recall@10 | candidate_recall@20 | candidate_negative_hit@20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| C: text query | 0.4800 | 0.5050 | 0.6400 | 0.7300 | 0.2500 |
| O: oracle gold query | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.1300 |

해석: 증상 인덱스 자체는 정답을 포함합니다. 실제 환자 문장을 그대로 query로 넣을 때 정답 후보 recall이 떨어지므로 표준화, alias, few-shot, domain phrase 보강 여지가 있습니다.

## Full Pipeline Baseline

운영에 가까운 흐름으로 Bedrock extraction, IR, Nova Pro top-k linker까지 실행했습니다.

### Pipeline Extraction

| Metric | Value |
| --- | ---: |
| pipeline_micro_f1 | 0.5274 |
| pipeline_macro_f1 | 0.4917 |
| pipeline_exact_match_rate | 0.4600 |
| validator_pass_rate | 0.9400 |
| error_rate | 0.0600 |
| false_positive_rate | 0.4301 |
| false_negative_rate | 0.5093 |

### IR + Linker From Pipeline Spans

| Metric | Value |
| --- | ---: |
| candidate_recall@3 | 0.5950 |
| candidate_recall@5 | 0.6200 |
| candidate_recall@10 | 0.7000 |
| candidate_recall@20 | 0.7750 |
| candidate_negative_hit@20 | 0.1800 |
| linker_micro_f1 | 0.8063 |
| linker_macro_f1 | 0.7150 |
| linker_exact_match_rate | 0.6900 |
| linker_false_positive_rate | 0.0723 |
| linker_false_negative_rate | 0.2870 |
| linker_invalid_count | 0 |

## Main Failure Buckets

- no prediction / missing gold after candidate search
- extraction normalized phrase does not map to current canonical symptom aliases
- adjacent symptom confusion: 가슴 답답 vs 흉통, 가래 vs 객혈/화농성 객담, 말초부종 vs 하지부종/사지 부종
- non-respiratory or broader symptoms need more alias/domain support: 방사통, 복부팽만감, 복부 통증, 설사, 피부홍조, 근육통, 오한

## Useful Files

- `pipeline/pipeline_summary.json`
- `pipeline/pipeline_stage_summary.json`
- `pipeline/pipeline_failure_cases.csv`
- `ir_from_pipeline/summary.json`
- `ir_from_pipeline/failure_cases.csv`
- `../baseline_20260626_fast/ir_candidate_only/summary.json`
- `../baseline_20260626_fast/ir_oracle_upper_bound/summary.json`
