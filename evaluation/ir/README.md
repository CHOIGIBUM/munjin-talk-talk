# 문진톡톡 IR 평가

이 디렉터리는 문진톡톡의 **표준 증상 매칭 성능**을 확인하기 위한 평가 코드입니다.

평가 목적은 LLM이 만든 증상 표현을 바로 신뢰하지 않고, 표준 증상 목록 안에서 얼마나 안정적으로 매칭되는지 검증하는 것입니다. 운영 파이프라인과 같은 입력 흐름을 사용해 `normalized_text`, `symptom_hint`, `status`를 만들고, 그 결과를 Hybrid IR과 Nova Pro linker에 넣어 최종 표준 증상 선택 성능을 계산합니다.

---

## 채택된 평가 구조

```text
환자 발화
  → 운영 파이프라인 기반 표준화·의미 span 추출
  → active symptom span만 IR 입력으로 사용
  → query = normalized_text + symptom_hint
  → BM25 + Titan Vector + label signal
  → RRF hybrid rank fusion
  → top-20 표준 증상 후보
  → Nova Pro final linker
  → 후보 밖 선택 금지 validator
```

이 구조의 핵심은 두 가지입니다.

- IR은 표준 증상 후보를 좁힙니다.
- LLM linker는 후보 안에서만 최종 증상을 고릅니다.

따라서 LLM이 표준 목록에 없는 증상명을 임의로 만드는 위험을 줄이고, 검색 실패와 최종 선택 실패를 분리해 분석할 수 있습니다.

---

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `run_pipeline_eval.py` | 원본 평가 문장을 운영 파이프라인에 넣어 `normalized_text`, `span`, `symptom_hint`를 생성 |
| `run_ir_eval.py` | 파이프라인이 만든 span으로 IR 후보 검색과 LLM linker 평가 수행 |
| `run_eval_suite.py` | 파이프라인 생성과 IR 평가를 이어서 실행하는 보조 스크립트 |
| `data/eval_cases.sample.jsonl` | 공개 가능한 샘플 평가 데이터 |
| `data/eval_cases.jsonl` | 실제 평가 데이터 위치. 개인정보나 저작권 이슈가 있으면 Git에 올리지 않음 |
| `outputs/` | 실행 결과 저장 위치. 원칙적으로 Git 관리 대상이 아님 |

---

## 평가 데이터 형식

평가 데이터에는 환자 발화와 정답 표준 증상명만 둡니다.
`query term`, `normalized_text`, `LLM symptom name`은 사람이 미리 적지 않고 실제 파이프라인을 돌려 생성합니다.

```json
{
  "case_id": "eval_001",
  "visit_type": "초진",
  "dialect_type": "standard",
  "question_id": "Q1",
  "text": "어제부터 목이 칼칼하고 코가 막혀요.",
  "gold_symptoms": ["목의 통증", "코막힘"],
  "negative_symptoms": []
}
```

`gold_symptoms`와 `negative_symptoms`는 `backend/serverless/src/data/symptom_index.json`에 존재하는 표준 증상명이어야 합니다.

---

## 1단계: 파이프라인 입력 생성

먼저 평가 문장을 운영 파이프라인에 통과시켜 IR 평가용 span을 만듭니다.

```powershell
cd C:\Users\CGB\munjin-talk-talk-mvp

python evaluation\ir\run_pipeline_eval.py `
  --input evaluation\ir\data\eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\pipeline
```

주요 출력 파일은 다음과 같습니다.

| 파일 | 확인 내용 |
| --- | --- |
| `pipeline_ir_eval_cases.jsonl` | IR 평가에 바로 넣을 span 기반 데이터 |
| `pipeline_case_results.jsonl` | 케이스별 전체 파이프라인 결과 |
| `pipeline_stage_summary.json` | validator 통과율, active span 비율, 매칭 가능 케이스 수 |
| `pipeline_span_diagnostics.csv` | span의 `type`, `status`, `normalized_text`, `name` |
| `pipeline_failure_cases.csv` | 실패 단계와 실패 사유 |

---

## 2단계: IR + Linker 평가

기본 실행은 제출 기준으로 채택한 `RRF hybrid + top-20 + Nova Pro linker`입니다.

```powershell
python evaluation\ir\run_ir_eval.py `
  --input evaluation\ir\outputs\pipeline\pipeline_ir_eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\ir_g_rrf_top20
```

위 명령은 내부적으로 다음 설정을 사용합니다.

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--variants` | `G` | IR top-k 후보 안에서 Pro LLM linker가 최종 증상을 선택 |
| `--top-k` | `20` | 후보 20개를 linker에게 전달 |
| `--score-mode` | `rrf-hybrid` | BM25, Vector, label signal 순위를 RRF로 융합 |
| `--embedding-provider` | `bedrock-titan` | 운영과 같은 Titan embedding 사용 |

IR 후보군만 빠르게 확인할 때는 LLM linker를 끕니다.

```powershell
python evaluation\ir\run_ir_eval.py `
  --input evaluation\ir\outputs\pipeline\pipeline_ir_eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\ir_candidate_only `
  --skip-llm-judge
```

---

## 결과 해석

먼저 `summary.json`을 봅니다.

| 지표 | 의미 |
| --- | --- |
| `candidate_recall@20` | IR 후보 20개 안에 정답 증상이 들어왔는지 확인 |
| `candidate_negative_hit@20` | 들어오면 안 되는 부정/호전 증상이 후보에 섞였는지 확인 |
| `linker_micro_f1` | Pro linker의 최종 선택을 전체 TP/FP/FN 기준으로 평가 |
| `linker_macro_f1` | 케이스별 F1 평균 |
| `linker_exact_match_rate` | 예측 증상 집합과 정답 증상 집합이 완전히 같은 비율 |
| `linker_false_positive_rate` | 최종 선택 중 오답 비율 |
| `linker_false_negative_rate` | gold 중 놓친 증상 비율 |

그다음 `failure_cases.csv`와 `candidates.csv`를 봅니다.

| 파일 | 보는 법 |
| --- | --- |
| `failure_cases.csv` | 정답이 top-k에 없어서 실패했는지, 후보 안에 있었지만 linker가 고르지 못했는지 구분 |
| `candidates.csv` | 각 후보의 BM25, vector, label, rank score, linker 선택 여부와 이유 확인 |

제출 자료에는 `candidate_recall@20`과 `linker_micro_f1`을 함께 제시합니다. 전자는 후보 검색 성능, 후자는 최종 표준 증상 선택 성능을 보여줍니다.

---

## Git 관리 기준

- 공개 가능한 샘플 데이터와 평가 코드만 커밋합니다.
- 실제 평가 데이터, Bedrock 응답 trace, 환자 발화 원문, 실행 결과물은 공개 저장소에 올리지 않습니다.
- `evaluation/ir/outputs/`와 `evaluation/ir/cache/`는 실행 산출물이므로 원칙적으로 커밋하지 않습니다.
