# 문진톡톡 사투리 RAG 의미 보존 평가팩

이 폴더는 문진톡톡의 사투리 RAG 보조 변환을 평가하기 위한 자료를 모은 곳입니다. 서비스의 최종 의료 판단 성능을 평가하는 폴더가 아니라, 사투리/구어체 문진 답변을 표준어 보조 문장으로 바꾸는 과정에서 환자 발화의 의미가 유지되는지 점검합니다.

## 평가 목적

문진톡톡은 고령 환자가 말한 답변을 의료진이 확인하기 쉬운 문장과 구조화 결과로 정리합니다. 이때 환자 발화에는 강원 사투리, 구어체, 축약 표현, 지역 표현이 섞일 수 있습니다.

사투리 RAG의 역할은 다음과 같습니다.

- 환자 원문에서 방언 표현과 가까운 항목을 찾습니다.
- `dialect_packs/dialect_kangwon.json`의 표준어 후보를 Bedrock 프롬프트에 힌트로 전달합니다.
- 힌트는 어휘 이해를 돕기 위한 참고 정보로만 쓰고, 원문에 없는 증상이나 사실을 추가하지 않도록 제한합니다.
- 최종 의료 판단은 하지 않으며, 표준어 보조 문장 생성과 이후 구조화의 안정성을 돕습니다.

따라서 이 평가의 핵심 질문은 다음과 같습니다.

```text
사투리/구어체 문진 답변을 표준어로 바꿨을 때
증상, 부정 표현, 시작/지속/호전/악화, 정도, 복약 사실, 질문 의도가 보존되는가?
```

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

| 파일 | 역할 |
| --- | --- |
| `run_dialect_semantic_eval.py` | RAG 힌트 검색, Bedrock 표준어 변환, Bedrock judge 평가를 수행하는 스크립트 |
| `data/dialect_norm_eval_200.jsonl` | 200개 평가 케이스 원본 |
| `data/dialect_norm_eval_200_preview.csv` | 평가 데이터 일부를 표 형태로 확인하기 위한 미리보기 |
| `reports/summary.json` | 제출용 요약 지표 |
| `reports/failed_cases.csv` | 실패 케이스만 모은 검토용 CSV |

스크립트를 새로 실행하면 `dialect_semantic_summary.json`, `dialect_semantic_case_results.jsonl`, `dialect_semantic_case_results.csv`, `dialect_semantic_failed_cases.csv`가 생성됩니다. 전체 case 결과는 파일이 커지고 검토성이 낮으므로, 제출용 브랜치에는 요약 지표와 실패 케이스 중심으로 남깁니다.

## 평가 데이터 구조

`data/dialect_norm_eval_200.jsonl`은 한 줄에 하나의 JSON 객체를 담습니다.

```json
{
  "case_id": "dialect_norm_001",
  "source_case_id": "eval_001",
  "source": "munjin_eval_original_plus_rule_gold",
  "visit_type": "초진",
  "dialect_type": "dialect",
  "question_id": "Q1",
  "text": "가만있어도 숨이 차서 데우 힘들어요.",
  "dialect_text": "가만있어도 숨이 차서 데우 힘들어요.",
  "gold_standard_text": "가만있어도 숨이 차서 매우 힘들어요.",
  "expected_replacements": [
    {
      "source_quote": "데우",
      "standard_text": "매우"
    }
  ],
  "gold_symptoms": ["호흡곤란"],
  "negative_symptoms": [],
  "note": "원 업로드 평가문장을 표준어 정답 문장으로 확장한 synthetic regression case"
}
```

| 필드 | 의미 |
| --- | --- |
| `case_id` | 평가 케이스 식별자 |
| `source_case_id` | 원본 평가 케이스 식별자 |
| `source` | 데이터 생성 또는 확장 출처 |
| `visit_type` | 초진/재진 구분 |
| `dialect_type` | `dialect` 또는 `standard` 구분 |
| `question_id` | 문진 질문 번호 |
| `text`, `dialect_text` | 평가에 넣는 환자 발화 문장 |
| `gold_standard_text` | 의미를 보존한 기준 표준어 문장 |
| `expected_replacements` | 기대되는 방언-표준어 치환 힌트 |
| `gold_symptoms` | 문장에 포함된 기준 증상 힌트 |
| `negative_symptoms` | 들어가면 안 되는 증상 힌트 |
| `note` | 데이터 생성 메모 |

평가 데이터는 synthetic/starter set입니다. 실제 병원 전체 실데이터나 임상 진단 정답 데이터가 아닙니다.

## 평가 파이프라인

```text
1. 평가 입력 로드
   dialect_text 또는 text를 환자 원문으로 사용

2. 사투리 RAG 힌트 검색
   backend/serverless/src/dialect_rag.py의 retrieve_dialect_context() 호출
   dialect_packs/dialect_kangwon.json에서 exact/partial match 후보 검색

3. 표준어 보조 문장 생성
   Bedrock Nova Lite가 standardized_text와 reason을 JSON으로 반환
   프롬프트에는 "원문에 없는 증상·약·시점·정도를 추가하지 말라"는 제한 포함

4. 의미 보존 judge
   Bedrock Nova Lite judge가 원문, 기준 표준어 문장, 모델 변환문을 비교
   same_meaning, standard_korean, added_fact, omitted_fact를 판정

5. 결과 집계
   semantic_success_rate와 실패 유형별 건수를 summary로 저장
   실패 케이스는 CSV로 별도 저장
```

## 성공 판정 기준

한 케이스는 아래 네 조건을 모두 만족해야 성공입니다.

| 조건 | 성공 기준 |
| --- | --- |
| `same_meaning` | 증상, 부정 표현, 시작/지속/호전/악화, 정도, 복약 사실, 질문 의도가 유지됨 |
| `standard_korean` | 변환문이 자연스러운 표준어 문장임 |
| `added_fact` | 원문/정답에 없는 증상, 약, 시점, 정도, 확신, 질문이 추가되지 않음 |
| `omitted_fact` | 원문/정답에 있던 증상, 부정, 시점, 정도, 복약 사실, 질문 의도가 빠지지 않음 |

스크립트 내부 성공식은 다음과 같습니다.

```text
semantic_success =
  same_meaning is true
  and standard_korean is true
  and added_fact is false
  and omitted_fact is false
```

## 현재 요약 지표

`reports/summary.json` 기준입니다.

| 항목 | 값 |
| --- | ---: |
| 평가 케이스 수 | 200 |
| 변환 모델 | `apac.amazon.nova-lite-v1:0` |
| Judge 모델 | `apac.amazon.nova-lite-v1:0` |
| 의미 성공률 | 0.900 |
| 동일 의미 판정률 | 0.925 |
| 표준어 판정률 | 0.990 |
| 정보 추가 없음 | 0.965 |
| 정보 누락 없음 | 0.930 |
| 평균 RAG 힌트 수 | 0.275 |

지표 해석:

- `semantic_success_rate`: 네 성공 조건을 모두 만족한 비율입니다.
- `same_meaning_rate`: 원문과 생성문의 핵심 의미가 같다고 judge가 본 비율입니다.
- `standard_korean_rate`: 생성문이 표준어 문장으로 자연스럽다고 본 비율입니다.
- `no_added_fact_rate`: 원문에 없던 증상, 복약, 시점, 정도 등이 추가되지 않은 비율입니다.
- `no_omitted_fact_rate`: 원문에 있던 정보가 빠지지 않은 비율입니다.
- `avg_rag_hint_count`: 한 케이스당 검색된 방언 힌트 평균입니다. 모든 케이스에 힌트가 붙는 것은 아니며, 표준어 문장이나 방언팩에 없는 표현은 힌트 없이 평가될 수 있습니다.

## 실패 유형

`summary.json`의 실패 유형 집계는 다음과 같습니다.

| 실패 유형 | 건수 | 의미 |
| --- | ---: | --- |
| `added_fact` | 7 | 원문에 없던 증상, 정도, 사실이 추가됨 |
| `omitted_fact` | 10 | 원문에 있던 정도, 부정, 시점, 질문 의도 등이 누락됨 |
| `meaning_mismatch` | 1 | 변환문이 원문과 다른 의미가 됨 |
| `not_standard_korean` | 2 | 의미는 대체로 유지됐지만 표준어 문장으로 부자연스러움 |
| `ok` | 180 | 성공 케이스 |

주의할 점은 `failure_type`이 대표 실패 유형이라는 점입니다. 한 케이스에서 정보 추가와 누락이 동시에 발생할 수 있으며, 스크립트는 `added_fact`, `omitted_fact`, `meaning_mismatch`, `not_standard_korean` 순서로 대표 유형을 붙입니다.

실패 분석은 `reports/failed_cases.csv`를 봅니다. 이 파일에는 다음 열이 들어 있습니다.

| 열 | 내용 |
| --- | --- |
| `case_id` | 실패 케이스 식별자 |
| `dialect_type` | 사투리/표준어 구분 |
| `semantic_success` | 최종 성공 여부 |
| `same_meaning`, `standard_korean`, `added_fact`, `omitted_fact` | judge 세부 판정 |
| `failure_type` | 대표 실패 유형 |
| `rag_hint_count` | 해당 케이스에서 검색된 RAG 힌트 수 |
| `original_text` | 환자 원문 |
| `gold_standard_text` | 기준 표준어 문장 |
| `predicted_standard_text` | 모델이 생성한 표준어 문장 |
| `normalizer_reason` | 변환 모델의 설명 |
| `judge_reason` | judge의 실패/성공 근거 |

예를 들어 `dialect_norm_002`는 "사래가 자주 걸려요"가 "콧물이 자주 나요"로 바뀌면서 의미가 달라진 케이스입니다. 이런 사례는 단순 표준어 자연성보다 의료 문진 의미 보존이 더 중요하다는 점을 보여줍니다.

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

Windows PowerShell에서는 환경변수를 다음처럼 설정할 수 있습니다.

```powershell
$env:AWS_PROFILE="<your-profile>"
$env:AWS_REGION="ap-northeast-2"
$env:AWS_DEFAULT_REGION="ap-northeast-2"
$env:DIALECT_SEMANTIC_MODEL_ID="apac.amazon.nova-lite-v1:0"
$env:DIALECT_SEMANTIC_JUDGE_MODEL_ID="apac.amazon.nova-lite-v1:0"
```

## 평가 실행

```bash
python evaluation/dialect_rag/run_dialect_semantic_eval.py \
  --input evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl \
  --output-dir evaluation/dialect_rag/reports/run_latest
```

일부 케이스만 빠르게 확인하려면 `--limit`을 사용할 수 있습니다.

```bash
python evaluation/dialect_rag/run_dialect_semantic_eval.py \
  --input evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl \
  --output-dir evaluation/dialect_rag/reports/run_sample \
  --limit 20
```

새 실행 결과를 제출용 파일로 갱신하려면 `run_latest/dialect_semantic_summary.json`을 `reports/summary.json`에, `run_latest/dialect_semantic_failed_cases.csv`를 `reports/failed_cases.csv`에 반영합니다. 단, Bedrock judge를 사용하므로 재실행 시 모델 응답 변동이 있을 수 있습니다.

## Git 관리 기준

커밋 권장:

- `evaluation/dialect_rag/README.md`
- `evaluation/dialect_rag/run_dialect_semantic_eval.py`
- `evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl`
- `evaluation/dialect_rag/data/dialect_norm_eval_200_preview.csv`
- `evaluation/dialect_rag/reports/summary.json`
- `evaluation/dialect_rag/reports/failed_cases.csv`

커밋 비권장:

- `evaluation/dialect_rag/reports/run_latest/`
- 전체 raw case result
- Bedrock 원문 응답 trace
- 환자 개인정보나 외부 공개 범위가 불명확한 원천 데이터

## 해석 시 주의

이 평가는 사투리 RAG 보조 변환의 의미 보존 점검입니다. 병원 실데이터 전체 성능, 임상 일반화 성능, 진단 정확도, 처방 정확도를 주장하는 벤치마크가 아닙니다.

발표나 제출에서는 다음처럼 말하는 것이 안전합니다.

```text
문진톡톡은 사투리/구어체 답변을 표준어 보조 문장으로 변환하는 과정에서
의미 보존, 정보 추가 방지, 정보 누락 방지를 별도 지표로 평가했다.
현재 공개 브랜치에는 200개 starter set 기준 평가 데이터와 실패 케이스를 함께 남겨
성능 주장과 한계를 같이 확인할 수 있게 했다.
```
