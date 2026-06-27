# Separated Evaluation Report

- generated_at: `2026-06-26T06:10:14.124246+00:00`
- dataset: `evaluation/hybrid_ir_pipeline/train_100_v2/train_100_v2.jsonl`
- dataset_rows: `100`
- held_out_test: `False`

이 리포트는 Hybrid IR 후보 검색, 사투리 RAG hint, Bedrock 파이프라인 통합을 분리해서 본 실행 결과입니다. 최종 held-out 성능이 아니라 `train_100_v2` 개발용 데이터셋 기반 파이프라인 점검 결과입니다.

## Track A - Offline IR

Bedrock을 호출하지 않습니다. alias hint와 local BM25 symptom reference를 결합해 정답 표준 증상이 후보군 안에 들어오는지 확인합니다.

| ranking | recall@1 | recall@3 | recall@5 | recall@10 | all_gold_hit@5 | negative_in_top5_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| alias | 0.8198 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.5000 |
| bm25 | 0.5045 | 0.8108 | 0.8829 | 0.9459 | 0.8700 | 0.6364 |
| combined | 0.8198 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.7727 |

해석:

- combined recall@5가 1.0이므로 이 데이터셋에서는 후보 검색 단계에서 정답 표준 증상이 빠지는 문제가 관찰되지 않았습니다.
- alias와 BM25 결합은 broad query에서 후보 회수 안정성을 높였습니다.
- 이 결과는 최종 모델 성능이 아니라 후보 검색 품질입니다.

## Track B - Dialect RAG

| 항목 | 값 |
| --- | ---: |
| Gangwon rows | 50 |
| rag_pack_anchored recall | 1.0000 (10/10) |
| non-anchor hint rate | 0.0000 (0/40) |

해석:

- 방언팩 anchor가 명시된 10건에서는 기대 힌트가 모두 검색되었습니다.
- anchor가 없는 강원식 구어체 40건에서는 불필요한 방언 hint가 검색되지 않았습니다.
- 이 결과는 "강원식 말투 전체가 방언팩으로 근거화된다"는 뜻이 아니라, source layer를 분리했을 때 RAG hint 개입이 통제되었다는 뜻입니다.

## Track C - Pipeline Integration

| 항목 | 값 |
| --- | ---: |
| persistence | `monkeypatched_no_s3_dynamodb` |
| rows completed | 100/100 |
| precision | 1.0000 |
| recall | 0.9279 |
| F1 | 0.9626 |
| schema/runtime failures | 0 |
| source quote grounding rate | 1.0000 |
| RAG context node seen rate | 1.0000 |
| negative false-positive rate | 0.0000 |

해석:

- Bedrock extraction과 LangGraph 파이프라인은 100건 모두 schema/runtime failure 없이 완료되었습니다.
- 생성된 근거 quote는 환자 원문에 모두 존재했습니다.
- 부정 증상을 active symptom으로 잘못 올린 사례는 관찰되지 않았습니다.
- recall 손실은 개선/해소 계열 정책 mismatch에 집중되어 있습니다.

## Interpretation

- Track A는 candidate-search quality입니다. 최종 모델 F1로 말하면 안 됩니다.
- Track B는 사투리 RAG hint의 anchor 기반 개입 타당성을 확인합니다.
- Track C는 이 브랜치에서 실제 Bedrock 파이프라인 성능에 가장 가까운 결과입니다.
- 단, 이 run은 locked held-out test가 아니라 `train_100_v2` 기준입니다.
- 남은 8건의 false negative는 모두 `progress_improved` 또는 `symptom_absent` 계열입니다. 제품 정책상 이 항목들은 active symptom `matched_slots`로 올리지 않고 follow-up context 또는 clinical clue로 보존하는 쪽에 가깝기 때문에, 후보 검색 실패보다 scoring-policy mismatch로 해석합니다.

## Reporting Guidance

발표에서는 다음처럼 말하는 것이 안전합니다.

```text
train_100_v2 기준 분리 평가에서 Offline IR combined recall@5는 1.0,
Dialect RAG anchored recall은 1.0,
Pipeline Integration F1은 0.9626이었다.
남은 false negative는 active symptom 정책과 평가 라벨 기준의 차이로 분석했다.
```

held-out reporting은 별도 `test_1000_v2` 생성, freeze, 첫 실행 리포트 보관 이후에만 수행해야 합니다.
