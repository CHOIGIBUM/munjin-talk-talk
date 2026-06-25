# 문진톡톡 IR 평가

이 폴더는 문진톡톡의 표준 증상 매칭 성능을 확인하기 위한 평가 코드입니다. 목표는 LLM이 만든 증상 표현을 그대로 믿지 않고, 표준 증상 목록 안에서 얼마나 안정적으로 후보를 찾고 최종 선택하는지 확인하는 것입니다.

---

## 1. 평가 구조

평가는 운영 파이프라인과 같은 입력 구조를 최대한 따릅니다.

```text
평가 문장
  -> 운영 파이프라인 기반 표준화/의미 span 추출
  -> active symptom span만 IR 입력
  -> query = normalized_text + symptom_hint
  -> BM25 + Titan Vector + label signal
  -> RRF hybrid ranking
  -> top-20 표준 증상 후보
  -> Nova Pro linker
  -> 후보 밖 선택 금지 validator
  -> 최종 표준 증상 평가
```

평가는 두 층으로 나눠 봅니다.

| 층 | 질문 |
| --- | --- |
| 후보 검색 | 정답 표준 증상이 top-k 후보 안에 들어왔는가 |
| 최종 선택 | 후보 중에서 linker가 실제 정답을 선택했는가 |

---

## 2. 파일 구성

| 파일 | 역할 |
| --- | --- |
| `run_pipeline_eval.py` | 평가 문장을 운영 파이프라인에 넣어 `normalized_text`, `status`, `symptom_hint` 생성 |
| `run_ir_eval.py` | 생성된 span으로 IR 후보 검색과 Linker 평가 수행 |
| `run_eval_suite.py` | 파이프라인 생성과 IR 평가를 이어서 실행하는 보조 스크립트 |
| `run_baseline.ps1` | 데이터 검증, 빠른 IR baseline, 선택적 전체 파이프라인 baseline을 한 번에 실행 |
| `validate_eval_data.py` | gold/negative 증상명과 방문유형-문항 조합 검증 |
| `data/eval_cases.sample.jsonl` | 공개 가능한 샘플 평가 데이터 |
| `data/eval_cases.json` | 현재 baseline 평가에 사용하는 100건 합성 데이터셋 |
| `outputs/` | 실행 결과. baseline 비교가 필요하면 함께 커밋 가능 |
| `cache/` | embedding cache. Git 관리 대상 아님 |

---

## 3. 평가 데이터 형식

평가 데이터에는 환자 발화와 정답 표준 증상명만 넣습니다. `normalized_text`, `symptom_hint`, query term은 사람이 미리 쓰지 않고 실제 파이프라인으로 생성합니다.

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

`gold_symptoms`와 `negative_symptoms`는 운영 `symptom_index.json`에 존재하는 표준 증상명이어야 합니다.

---

## 4. 실행 순서

### 1단계: 파이프라인 span 생성

```powershell
cd C:\Users\CGB\munjin-talk-talk-mvp

python evaluation\ir\run_pipeline_eval.py `
  --input evaluation\ir\data\eval_cases.json `
  --output-dir evaluation\ir\outputs\pipeline
```

주요 출력:

| 파일 | 내용 |
| --- | --- |
| `pipeline_ir_eval_cases.jsonl` | IR 평가에 넣을 span 데이터 |
| `pipeline_case_results.jsonl` | 케이스별 파이프라인 전체 결과 |
| `pipeline_stage_summary.json` | validator 통과율, active span 수, 실패 수 |
| `pipeline_span_diagnostics.csv` | span별 type, status, quote, normalized text |
| `pipeline_failure_cases.csv` | 실패 단계와 사유 |

### 2단계: IR + Linker 평가

채택 기준 실험은 RRF hybrid, top-20, Nova Pro linker입니다.

```powershell
python evaluation\ir\run_ir_eval.py `
  --input evaluation\ir\outputs\pipeline\pipeline_ir_eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\ir_g_rrf_top20
```

IR 후보만 확인할 때:

```powershell
python evaluation\ir\run_ir_eval.py `
  --input evaluation\ir\outputs\pipeline\pipeline_ir_eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\ir_candidate_only `
  --skip-llm-judge
```

### 한 번에 baseline 돌리기

LLM 없이 빠르게 IR 후보군 baseline과 oracle upper-bound를 확인합니다.

```powershell
.\evaluation\ir\run_baseline.ps1 `
  -InputPath evaluation\ir\data\eval_cases.json `
  -OutputDir evaluation\ir\outputs\baseline_20260626_fast
```

Bedrock extraction/linker까지 포함해 전체 운영 흐름을 확인하려면 `-FullPipeline`을 붙입니다.

```powershell
.\evaluation\ir\run_baseline.ps1 `
  -InputPath evaluation\ir\data\eval_cases.json `
  -OutputDir evaluation\ir\outputs\baseline_20260626_full `
  -FullPipeline
```

---

## 5. 주요 지표

| 지표 | 의미 |
| --- | --- |
| `candidate_recall@20` | IR top-20 후보 안에 정답 표준 증상이 들어온 비율 |
| `candidate_negative_hit@20` | 부정/호전 등 들어오면 안 되는 증상이 후보에 섞인 비율 |
| `linker_micro_f1` | 최종 선택 결과를 전체 TP/FP/FN 기준으로 평가 |
| `linker_macro_f1` | 케이스별 F1 평균 |
| `linker_exact_match_rate` | 예측 증상 집합과 정답 집합이 완전히 같은 비율 |
| `linker_false_positive_rate` | 최종 선택 중 오답 비율 |
| `linker_false_negative_rate` | gold 중 놓친 증상 비율 |

해커톤 발표에서는 후보 검색 성능과 최종 선택 성능을 분리해 설명하는 것이 좋습니다. `candidate_recall@20`은 IR이 보기 후보를 얼마나 잘 올리는지, `linker_micro_f1`은 최종 표준 증상 선택이 얼마나 정확한지를 보여줍니다.

---

## 6. 결과 파일 해석

| 파일 | 보는 법 |
| --- | --- |
| `summary.json` | 전체 지표 요약 |
| `candidates.csv` | 후보별 BM25, vector, label, RRF rank, linker 선택 여부 |
| `failure_cases.csv` | 정답이 후보 안에 없어서 실패했는지, 후보 안에 있었지만 linker가 고르지 못했는지 구분 |

성능 개선 시 먼저 `failure_cases.csv`를 봅니다.

- 정답이 top-20 안에 없으면 IR 후보 검색 문제입니다.
- 정답이 top-20 안에 있는데 linker가 못 고르면 linker prompt 또는 validator 문제입니다.
- active span 자체가 없으면 extraction 또는 status tagging 문제입니다.

---

## 7. Git 관리 기준

공개 저장소에는 평가 코드와 합성 테스트 데이터를 포함합니다. 현재 100건 데이터는 실제 환자 데이터가 아닌 테스트 데이터이므로 Git에 올릴 수 있습니다.

커밋하지 않는 항목:

```text
evaluation/ir/cache/
```

`outputs/`는 baseline 비교가 필요할 때 커밋할 수 있습니다. 단, 실제 운영 데이터나 민감한 trace가 섞였을 때는 커밋하지 않습니다.
