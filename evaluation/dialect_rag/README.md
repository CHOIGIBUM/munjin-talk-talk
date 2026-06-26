# 문진톡톡 사투리 RAG 의미 평가팩

이 브랜치는 사투리 문진 문장을 표준어 보조 문장으로 변환했을 때 원래 의미가 유지되는지 확인하기 위한 실험 브랜치입니다. 실제 서비스 코드 변경을 위한 브랜치가 아니라, `backend/serverless/src/dialect_normalization.py`와 Bedrock 기반 RAG 보조 변환을 평가한 기록을 정리합니다.

## 파일 구성

```text
evaluation/dialect_rag/
├── README.md
├── run_dialect_semantic_eval.py
├── data/
│   ├── dialect_norm_eval_200.jsonl
│   └── dialect_norm_eval_200_preview.csv
└── reports/
    ├── summary.json
    └── failed_cases.csv
```

- `data/dialect_norm_eval_200.jsonl`: 사투리 입력, 기준 표준어 문장, 기대 증상 힌트를 포함한 200개 평가 케이스입니다.
- `reports/summary.json`: 제출용 요약 지표입니다.
- `reports/failed_cases.csv`: 의미 불일치, 정보 추가/누락 등 실패 케이스만 추린 표입니다.
- 원시 전체 케이스 결과(`dialect_semantic_case_results.*`)는 파일이 커지고 검토성이 낮아 커밋 대상에서 제외합니다.

## 실행 준비

프로젝트 루트에서 실행한다고 가정합니다.

```bash
cd munjin-talk-talk

export AWS_PROFILE=<your-profile>
export AWS_REGION=ap-northeast-2
export AWS_DEFAULT_REGION=ap-northeast-2
export DIALECT_SEMANTIC_MODEL_ID=apac.amazon.nova-lite-v1:0
export DIALECT_SEMANTIC_JUDGE_MODEL_ID=apac.amazon.nova-lite-v1:0
```

필요 패키지는 백엔드 서버리스 환경과 동일하게 맞춥니다.

```bash
pip install -r backend/serverless/src/requirements.txt
```

## 평가 실행

```bash
python evaluation/dialect_rag/run_dialect_semantic_eval.py \
  --input evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl \
  --output-dir evaluation/dialect_rag/reports/run_latest
```

스크립트는 Bedrock 모델 응답과 judge 결과를 함께 저장합니다. 새 실행 결과 중 전체 원시 케이스 파일은 기본적으로 커밋하지 않고, 발표나 제출에는 `summary.json`과 `failed_cases.csv`만 사용합니다.

## 현재 요약 지표

`reports/summary.json` 기준입니다.

| 항목 | 값 |
|---|---:|
| 평가 케이스 수 | 200 |
| 변환 모델 | `apac.amazon.nova-lite-v1:0` |
| Judge 모델 | `apac.amazon.nova-lite-v1:0` |
| 의미 성공률 | 0.900 |
| 동일 의미 판정률 | 0.925 |
| 표준어 판정률 | 0.990 |
| 정보 추가 없음 | 0.965 |
| 정보 누락 없음 | 0.930 |
| 평균 RAG 힌트 수 | 0.275 |

실패 유형은 `added_fact` 7건, `meaning_mismatch` 1건, `not_standard_korean` 2건, `omitted_fact` 10건입니다.

## 해석 시 주의

이 평가는 200개 synthetic/starter set에 대한 사투리 변환 의미 보존 점검입니다. 병원 실데이터 전체 성능이나 임상 일반화 성능을 주장하는 벤치마크가 아니며, Bedrock judge를 사용하므로 재실행 시 AWS 권한과 비용이 필요합니다.
