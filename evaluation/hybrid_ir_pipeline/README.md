# Hybrid IR 파이프라인 평가팩

이 브랜치는 문진톡톡의 증상 후보 검색, 사투리 RAG 힌트, Bedrock 기반 추출 파이프라인을 분리해서 점검한 실험 브랜치입니다. 실제 서비스 공식 코드 브랜치가 아니라, 성능 테스트와 재현 자료를 정리한 공간입니다.

## 파일 구성

```text
evaluation/hybrid_ir_pipeline/
├── README.md
├── run_separated_evaluation.py
├── blueprint/
│   ├── README.md
│   ├── case_blueprint.jsonl
│   ├── case_blueprint.schema.json
│   ├── distribution_plan.json
│   └── quality_gate_report.json
├── design/
│   ├── README.md
│   ├── evaluation_tracks.md
│   └── train_100_v2_blueprint_draft.md
├── train_100_v2/
│   ├── README.md
│   ├── train_100_v2.jsonl
│   ├── quality_gate_report.json
│   ├── artifact_build_report.json
│   ├── build_artifacts.py
│   └── render_train.py
└── reports/
    ├── metrics_summary.json
    ├── separated_evaluation_report.md
    └── pipeline_error_analysis.md
```

## 평가 트랙

| 트랙 | Bedrock 사용 | 의미 |
|---|---:|---|
| Track A: Offline IR | 아니오 | 정답 증상이 후보 리스트에 들어오는지 확인 |
| Track B: Dialect RAG | 아니오 | 강원 사투리 RAG 힌트가 의도한 row에서 검색되는지 확인 |
| Track C: Pipeline Integration | 예 | 실제 LangGraph/Bedrock 추출 파이프라인을 S3/DynamoDB 저장 없이 점검 |

## 현재 요약

`reports/metrics_summary.json` 기준입니다.

- 데이터: `evaluation/hybrid_ir_pipeline/train_100_v2/train_100_v2.jsonl`
- 행 수: 100
- Track A combined recall@5: 1.0
- Track B rag-pack anchored recall: 1.0
- Track C precision/recall/F1: 1.0 / 0.9279 / 0.9626
- schema/runtime failure: 0
- negative false-positive rate: 0.0

## 실행

프로젝트 루트에서 실행합니다.

```bash
python evaluation/hybrid_ir_pipeline/run_separated_evaluation.py \
  --dataset evaluation/hybrid_ir_pipeline/train_100_v2/train_100_v2.jsonl \
  --out-dir evaluation/hybrid_ir_pipeline/reports/run_latest
```

새 실행 결과의 상세 JSON 로그는 커밋하지 않고, 제출이나 발표에는 `reports/metrics_summary.json`, `reports/separated_evaluation_report.md`, `reports/pipeline_error_analysis.md`만 사용합니다.

## 해석 시 주의

현재 수치는 `train_100_v2` 기반 파이프라인 점검 결과입니다. 최종 모델 성능 또는 held-out 성능으로 표현하면 안 됩니다. 공개 가능한 최종 성능 주장은 별도 고정 테스트셋(`test_1000_v2` 등)을 만든 뒤 첫 실행 리포트를 저장한 후에 해야 합니다.
