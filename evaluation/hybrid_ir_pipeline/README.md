# 문진톡톡 Hybrid IR 파이프라인 평가 설명

이 문서는 `eval/hybrid-ir-pipeline` 브랜치에서 가장 먼저 읽어야 하는 평가 설명서입니다. 세부 설계 노트를 여러 README로 나누지 않고, 해커톤 심사위원이 바로 이해해야 할 질문에 집중합니다.

```text
이 평가는 "문진톡톡이 LLM에게 증상 판단을 전부 맡긴 서비스가 아니라,
후보 검색, 사투리 힌트, Bedrock 구조화 파이프라인을 분리해 검증한 서비스"임을 보여주기 위한 근거다.
```

## 이 평가가 보는 것

문진톡톡은 환자 발화를 바로 진단명이나 표준 증상명으로 확정하지 않습니다. 먼저 환자 말을 구조화하고, 표준 증상 후보를 검색하고, 그 후보 안에서 임상 정책에 맞는 슬롯만 최종 `matched_slots`로 올립니다.

그래서 평가는 한 덩어리 점수 대신 세 구간으로 나눴습니다.

| 트랙 | 무엇을 검증하나 | 왜 필요한가 |
| --- | --- | --- |
| Track A: Offline IR | 정답 표준 증상이 top-k 후보 안에 들어오는지 | 후보 검색 단계에서 이미 정답이 빠지는지 확인 |
| Track B: Dialect RAG | 강원 사투리 힌트가 필요한 행에서만 검색되는지 | 방언 RAG가 과하게 개입하거나 근거 없이 작동하지 않게 확인 |
| Track C: Pipeline Integration | Bedrock 추출, schema 검증, IR 링킹 후 최종 `matched_slots`가 맞는지 | 실제 서비스 파이프라인에 가장 가까운 통합 동작 확인 |

Track A는 검색 엔진의 후보 풀링 품질이고, Track C가 실제 파이프라인 성능에 더 가깝습니다. 따라서 Track A recall을 최종 모델 F1처럼 말하면 안 됩니다.

## 왜 분리 평가했나

LLM 기반 문진에서 위험한 지점은 하나가 아닙니다.

- 후보 검색이 정답 표준 증상을 아예 못 가져올 수 있습니다.
- 사투리 RAG가 필요 없는 문장에 힌트를 과하게 넣을 수 있습니다.
- Bedrock이 schema에 맞지 않는 출력을 만들 수 있습니다.
- 환자 원문에 없는 근거를 `source_quote`처럼 만들 수 있습니다.
- 이미 나아진 증상이나 부정 증상을 active symptom으로 올릴 수 있습니다.

이 브랜치는 위 위험을 한 점수로 뭉개지 않고, 어느 단계가 안정적인지 따로 보여주기 위해 만들었습니다.

## 데이터셋 요약

현재 결과는 `train_100_v2/train_100_v2.jsonl` 100건 기준입니다. 실제 환자 데이터가 아니라, 개발용 synthetic 문진 발화입니다.

| 항목 | 구성 |
| --- | --- |
| 방문/질문 | 초진 Q1 50건, 재진 Q3 50건 |
| 언어 스타일 | 표준어 50건, 강원식 구어체 50건 |
| 방언 source layer | none 50건, clinical_colloquial 25건, rag_pack_anchored 10건, light_dialect_style 15건 |
| 상태 패턴 | active_current, recurrent_or_persistent, improved_or_resolved, denied_negative_context, mixed_context |

중요한 점은 강원식 구어체 50건 전체를 방언팩 근거 사례로 주장하지 않는다는 것입니다. 실제 방언팩 anchor가 있는 10건만 `rag_pack_anchored`로 분리했고, Track B는 이 10건에서 기대 힌트가 검색되는지 봅니다.

## 결과 요약

고정 지표 파일은 [reports/metrics_summary.json](reports/metrics_summary.json)입니다.

| 지표 | 값 | 해석 |
| --- | ---: | --- |
| Track A combined recall@5 | 1.0000 | 정답 표준 증상이 top-5 후보에서 빠지지 않음 |
| Track B rag-pack anchored recall | 1.0000 | 방언팩 anchor 10건에서 기대 힌트 검색 성공 |
| Track B non-anchor hint rate | 0.0000 | anchor 없는 강원식 구어체에서 불필요한 힌트 없음 |
| Track C precision | 1.0000 | 최종 active symptom 오탐 없음 |
| Track C recall | 0.9279 | active 증상 기준 회수율 |
| Track C F1 | 0.9626 | Bedrock 통합 파이프라인 조화 평균 |
| schema/runtime failures | 0 | schema 또는 런타임 실패 없음 |
| source quote grounding rate | 1.0000 | 모든 근거 quote가 환자 원문에 존재 |
| negative false-positive rate | 0.0000 | 부정 증상을 active symptom으로 올린 사례 없음 |

상세 실행 결과는 [reports/separated_evaluation_report.md](reports/separated_evaluation_report.md)를 봅니다.

## 남은 8건 mismatch의 의미

Track C에서 남은 mismatch는 8건이며 모두 false negative입니다. 공통 패턴은 `progress_improved` 또는 `symptom_absent` 계열입니다.

예시:

- 인후통은 조금 나아졌지만 여전히 힘들 때가 있음
- 열이 나아진 것 같음
- 피로감은 완화됐지만 근육통은 현재 남음
- 목소리 변화가 조금 나아짐

이것은 단순한 IR 실패나 LLM 실패로 보기 어렵습니다. 문진톡톡의 제품 정책은 호전된 증상(`progress_improved`)이나 현재 없는 증상(`symptom_absent`)을 진료실 화면의 active symptom card로 올리지 않습니다. 대신 follow-up context 또는 clinical clue로 보존하는 방향에 가깝습니다.

따라서 남은 recall 손실은 다음처럼 해석합니다.

```text
평가셋의 gold label은 개선/해소 계열도 회수 대상으로 보았지만,
제품 정책은 해당 항목을 active symptom matched_slots에서 제외한다.
즉 남은 8건은 후보 검색 실패가 아니라 scoring-policy mismatch에 가깝다.
```

## 파일 구조

```text
evaluation/hybrid_ir_pipeline/
├── README.md
├── run_separated_evaluation.py
├── blueprint/
│   ├── case_blueprint.jsonl
│   ├── case_blueprint.schema.json
│   ├── distribution_plan.json
│   └── quality_gate_report.json
├── train_100_v2/
│   ├── train_100_v2.jsonl
│   ├── quality_gate_report.json
│   ├── artifact_build_report.json
│   ├── build_artifacts.py
│   └── render_train.py
└── reports/
    ├── metrics_summary.json
    └── separated_evaluation_report.md
```

보조 설계 README들은 이 문서로 통합했습니다. 심사위원은 루트 README와 이 문서, 결과 리포트만 읽으면 평가 의도와 결과를 이해할 수 있습니다.

## 실행 방법

프로젝트 루트에서 실행합니다.

```bash
python evaluation/hybrid_ir_pipeline/run_separated_evaluation.py \
  --dataset evaluation/hybrid_ir_pipeline/train_100_v2/train_100_v2.jsonl \
  --out-dir evaluation/hybrid_ir_pipeline/reports/run_latest
```

Track C는 Bedrock을 호출하므로 AWS 권한과 비용 영향이 있습니다. 실행별 raw output, Bedrock raw response trace, 임시 디렉터리는 공개 저장소에 커밋하지 않습니다.

## 발표용 요약 문장

```text
문진톡톡은 환자 발화를 LLM이 자유롭게 판단하게 두지 않고,
후보 검색, 사투리 RAG 힌트, Bedrock 구조화 파이프라인을 분리해 검증했다.
train_100_v2 기준 Offline IR combined recall@5는 1.0,
Pipeline Integration F1은 0.9626이었다.
남은 mismatch는 호전/해소 증상을 active symptom으로 올리지 않는 제품 정책 차이로 해석했다.
```

피해야 할 표현:

- 이 결과를 최종 held-out 성능이라고 말하기
- Track A recall을 전체 모델 F1이라고 말하기
- `train_100_v2`를 실제 환자 데이터라고 말하기
- 남은 false negative를 모두 시스템 오류라고 단정하기
