# Eval Clean Baseline Report

Date: 2026-06-26

Branch: `eval-clean`

## Scope

This branch resets the contaminated alias/few-shot experiment state and keeps
the early domain-specific few-shot structure from commit `3074384`.

Removed from the clean baseline:

- separate symptom alias bridge data and loader
- alias query expansion in IR
- alias-added BM25 document text
- failure-case-based few-shot additions after `3074384`
- contaminated alias/improvement output reports

Kept:

- production domain pack changes unrelated to the alias bridge
- curated 100-case public dev dataset
- 1000-case public synthetic regression dataset

## Dataset Validation

| Dataset | Cases | Visits | Q Mix | Dialect Mix | Gold Symptoms | Errors |
| --- | ---: | --- | --- | --- | ---: | ---: |
| `eval_cases.json` | 100 | 60 initial / 40 follow-up | 81 Q1 / 19 Q3 | 50 standard / 50 dialect | 47 | 0 |
| `synthetic_1000.json` | 1000 | 600 initial / 400 follow-up | 810 Q1 / 190 Q3 | 500 standard / 500 dialect | 47 | 0 |

The 1000-case set is balanced for symptom coverage: each gold symptom appears
31-33 times. It is not a blind benchmark because it has already been inspected
during alias/few-shot analysis.

## Candidate-Only IR Baseline

Variant C, top-k 20, no LLM linker.

| Dataset | Cases | R@3 | R@5 | R@10 | R@20 | NegativeHit@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100-case public dev | 100 | 0.7800 | 0.8200 | 0.8600 | 0.9250 | 0.2900 |
| 1000-case public regression | 1000 | 0.6235 | 0.6862 | 0.7742 | 0.8563 | 0.2500 |

## End-to-End Mini Pipeline Baseline

Input: first 30 cases from `eval_cases.json`

Pipeline output scored against gold symptoms:

| Metric | Value |
| --- | ---: |
| Pipeline Micro F1 | 0.7302 |
| Pipeline Macro F1 | 0.6556 |
| Pipeline Exact match | 0.6333 |
| Pipeline FPR | 0.2333 |
| Pipeline FNR | 0.3030 |
| Validator pass | 1.0000 |

IR/linker scored on pipeline-generated spans:

| Metric | Value |
| --- | ---: |
| Candidate Recall@3 | 0.9667 |
| Candidate Recall@5 | 0.9667 |
| Candidate Recall@10 | 0.9667 |
| Candidate Recall@20 | 1.0000 |
| Linker Micro F1 | 0.9697 |
| Linker Macro F1 | 0.9556 |
| Linker Exact match | 0.9333 |
| Linker FPR | 0.0303 |
| Linker FNR | 0.0303 |

## Interpretation

The clean baseline shows that candidate retrieval is not the main bottleneck
once the pipeline has produced usable active spans. The larger loss happens
before IR/linking: extraction, standardization, active/absent separation, and
specific symptom naming.

Future improvements should therefore be measured in three separate layers:

1. extraction/standardization pipeline F1
2. candidate retrieval Recall@k
3. linker final F1 on pipeline-generated spans

