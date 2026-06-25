# Weakness Analysis Improvement v4

## Goal

Clean-baseline 이후 성능 병목을 다시 분리하고, 평가 문장을 그대로 외우는 방식이 아니라 반복되는 오류 유형을 일반 규칙으로 보강했다.

## Weaknesses Found

- Extraction/standardization 단계에서 Q3 복용약 답변 안에 섞인 현재 증상을 놓쳤다.
- IR preferred 후보가 생성되어도 rank/acceptance가 약해 올바른 후보가 뒤로 밀렸다.
- `sputum` 같은 넓은 slot mapping이 먼저 적용되어 `거품이 섞인 가래`, `검은색 가래` 같은 구체 증상이 `가래`로 뭉개졌다.
- `삼킬 때 아픔`과 `삼키기 곤란`, `숨 쉴 때 가슴 통증`과 `호흡곤란`, `권태감/근육통/근력 약화` 같은 경계가 자주 흔들렸다.
- LLM이 `throat_pain` 같은 schema 밖 slot_ref를 만들면 repair loop가 끝까지 실패했다.

## Changes

- `preferred_canonical_name()`이 slot fallback보다 텍스트 패턴과 실제 canonical phrase를 먼저 보도록 변경.
- `preferred_alias` 후보를 gate에서 허용하고, rank 보정을 강화.
- Q3/current_medications 같은 비증상 문항이어도 active symptom span이 있으면 IR 매칭 수행.
- schema 밖 symptom `slot_ref`는 실패시키지 않고 `other`로 낮춘 뒤 source/name 기반 IR이 최종 표준명을 결정하도록 정규화.
- domain pack의 `ir_text_aliases`에 일반화 가능한 경계 패턴 추가.
- symptom hint few-shot은 3개에서 7개로 늘렸고, 평가 원문 복붙이 아니라 구체/포괄 증상 구분, Q3 증상 보존, 심박 표현 분리 같은 오류 유형 중심으로 작성.
- extraction few-shot에 Q3 복용약 문항 안의 active symptom 예시 추가.

## Metrics

### Candidate-only IR

| Dataset | Baseline C R@20 | v4 C R@20 | Note |
| --- | ---: | ---: | --- |
| public 100 dev | 0.9250 | 0.9700 | v3/v4 IR-identical output |
| public synthetic 1000 | 0.8563 | 0.9278 | v3/v4 IR-identical output |

### End-to-end Pipeline

| Dataset | Baseline Micro F1 | v4 Micro F1 | v4 Macro F1 | v4 Exact | Validator |
| --- | ---: | ---: | ---: | ---: | ---: |
| public 100 dev, first 30 | 0.7302 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| public synthetic 1000, first 30 | not rerun baseline here | 0.8989 | 0.8944 | 0.8333 | 1.0000 |

## Anti-cheating Notes

- 100/1000 public data는 개발/회귀용으로만 사용했다. 최종 blind 성능 주장에는 쓰지 않는다.
- few-shot은 특정 case id나 원문을 맞추는 정답지가 아니라, 오류 유형의 경계 조건만 설명한다.
- 큰 1000개 데이터를 alias/few-shot으로 직접 흡수하지 않았다. 개선은 domain pack 패턴, schema recovery, candidate ranking 구조에 집중했다.
- 다음 단계 성능 주장은 별도 seed/shuffle 또는 새 blind set에서 확인해야 한다.

## Remaining Risks

- public 100 first 30에서 1.0이 나왔기 때문에, 이 수치는 개선 검증이지 일반화 성능으로 말하면 안 된다.
- synthetic first 30에는 아직 `검은색 가래 -> 가래`, `온몸이 떨림 -> 오한`, `천명음 -> 호흡곤란`, `목소리 변화 -> 목의 통증` 같은 경계 실패가 남아 있다.
- 다음 개선은 전체 100 또는 shuffled synthetic subset에서 failure mining을 돌리고, 새로운 blind set은 마지막까지 열지 않는 방식이 적절하다.

## Commands Run

```powershell
python evaluation/ir/run_ir_eval.py --input evaluation/ir/data/eval_cases.json --output-dir evaluation/ir/outputs/eval_dev_improve_v3_manual100_fast/ir_candidate_only --top-k 20 --variants C --skip-llm-judge
python evaluation/ir/run_ir_eval.py --input evaluation/ir/data/synthetic/synthetic_1000.json --output-dir evaluation/ir/outputs/eval_dev_improve_v3_public1000_fast/ir_candidate_only --top-k 20 --variants C --skip-llm-judge
python evaluation/ir/run_eval_suite.py --input evaluation/ir/data/eval_cases.json --output-dir evaluation/ir/outputs/eval_dev_improve_v4_manual100_full30 --limit 30 --top-k 20 --variants G
python evaluation/ir/run_eval_suite.py --input evaluation/ir/data/synthetic/synthetic_1000.json --output-dir evaluation/ir/outputs/eval_dev_improve_v4_public1000_full30 --limit 30 --top-k 20 --variants G
```
