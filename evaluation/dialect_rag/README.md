# 문진톡톡 사투리 RAG 의미 보존 벤치마크 명세서

본 디렉터리(`evaluation/dialect_rag/`)는 고령 환자의 비정형 발화(강원 사투리, 구어체, 축약어)를 표준어 보조 문장으로 변환하는 파이프라인의 **의미적 무결성(Semantic Integrity)을 정량적으로 검증하기 위한 평가 패키지**입니다.

본 벤치마크는 최종 의료적 진단 정답률을 측정하는 임상 벤치마크와 역할을 엄격히 분리합니다. LLM이 환자의 일상 언어를 의학적 처리가 용이한 표준어로 정제하는 과정에서 **환자가 호소한 핵심 증상과 임상적 맥락이 손실 없이 보존되는가**를 검증합니다.

---

## 1. 평가 핵심 사상 및 검증 질문

고령 환자의 외래 문진 시연 환경에서는 "가만있어도 숨이 차서 데우 힘들어요", "매자지다" 등 지역적 특색이 강한 언어가 빈번하게 수신됩니다. 

백엔드 파이프라인 내 사투리 RAG(`retrieve_dialect_context`)는 강원 권역 방언 사전(`dialect_kangwon.json`)을 조작하여 표준어 변환 후보를 프롬프트 힌트로 주입합니다. 이때 프롬프트 규칙은 힌트를 **단순 어휘 해독용 참고 자산으로만 제한**하며, 원문에 존재하지 않는 증상이나 정도를 임의 생성하지 않도록 통제합니다.

따라서 본 평가가 입증하고자 하는 핵심 질문은 다음과 같습니다.

> **핵심 검증 명세 (Core Verification Contract)** >
> 사투리 및 구어체 답변을 표준어 문장으로 치환했을 때, > **[증상명, 부정 맥락, 시작·지속·호전·악화 시점, 고통의 정도, 복약 사실, 환자의 질문 의도]** 가 100% 왜곡 없이 보존되는가?

---

## 2. 디렉터리 및 아티팩트 구성

```text
evaluation/dialect_rag/
├── README.md
├── run_dialect_semantic_eval.py             # RAG 검색 + 표준어 변환 + LLM Judge 통합 실행기
├── data/
│   ├── dialect_norm_eval_200.jsonl          # 검증용 합성 문진 케이스 200건 (Master)
│   └── dialect_norm_eval_200_preview.csv    # 평가 데이터셋 시각적 검토용 프리뷰
└── reports/
    ├── summary.json                         # 공식 제출용 핵심 요약 지표 스냅샷
    └── failed_cases.csv                     # 실패 케이스 집중 분석용 인벤토리
```

> **엔지니어링 최적화 안내:** 스크립트 구동 시 전체 추론 본문(`*_case_results.jsonl`)이 산출되나, 파일 용량 비대화 및 Git 레포지토리 오염을 방지하기 위해 배포 브랜치에는 **공식 요약 지표(`summary.json`)와 실패 케이스 정밀 분석본(`failed_cases.csv`)만 확정 아티팩트로 유지**합니다.

---

## 3. 벤치마크 데이터 스키마

`data/dialect_norm_eval_200.jsonl` 파일에 적재되는 개별 평가 케이스 규격입니다. PII(개인식별정보) 유출 방지를 위해 실제 현장 임상 발화의 언어적 습관을 구조적으로 복제한 **합성 검증 데이터셋(Synthetic Starter Set)** 입니다.

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
  "note": "원 평가문장을 표준어 정답 문장으로 확장한 synthetic regression case"
}
```

| 필드명 | 데이터 타입 | 임상 및 평가 검증 역할 |
| --- | :---: | --- |
| `case_id` / `source_case_id` | String | 평가 케이스 고유 식별자 및 원본 대조 ID |
| `visit_type` / `dialect_type`| String | 초진·재진 문맥 및 방언(`dialect`) vs 표준어(`standard`) 속성 |
| `question_id` | String | 문진 질문 슬롯 번호 (예: `Q1`) |
| `text` / `dialect_text` | String | 파이프라인에 주입되는 환자의 Raw 발화 입력값 |
| `gold_standard_text` | String | 의미적 손실이 전혀 없는 임상 정답 기준 표준어 문장 |
| `expected_replacements` | Array | RAG 엔진이 선제적으로 타겟팅해야 하는 사투리-표준어 쌍 |
| `gold_symptoms` | Array | 발화 내에 반드시 추출되어야 하는 표준 증상 키워드 |
| `negative_symptoms` | Array | 환각(Hallucination)에 의해 삽입되면 안 되는 금지 증상 키워드 |

---

## 4. 5단계 평가 파이프라인 시퀀스

```text
[Step 01] 평가 입력 패치        ──> dialect_text 혹은 text를 환자 발화 원문으로 바인딩
[Step 02] 사투리 RAG 힌트 검색 ──> retrieve_dialect_context() 구동 (Exact/Partial 매칭)
[Step 03] 표준어 보조문 생성   ──> Bedrock Nova Lite 호출 (제약 조건 프롬프트 강제 제어)
[Step 04] 의미 보존 LLM Judge  ──> Nova Lite Judge가 [원문 vs Gold 정답 vs 생성문] 삼자 교차 검증
[Step 05] 아티팩트 최종 집계   ──> 성공률 산출 및 예외 CSV 파티셔닝 아카이빙
```

---

## 5. 엄격한 성공 판정 매트릭스

단일 테스트 케이스는 아래의 **4대 평가 지표를 단 하나도 누락 없이 100% 충족(AND 연산)해야만 최종 성공(`ok`)으로 확정**됩니다.

> **`Semantic Success`** = `same_meaning` ∧ `standard_korean` ∧ ¬`added_fact` ∧ ¬`omitted_fact`

| 평가 지표명 | 판정 기준 명세 | 임상적 방어 목표 |
| --- | --- | --- |
| `same_meaning` | 원문의 핵심 증상, 시점 변화, 복약 사실이 유지되었는가 | 문진 데이터의 본질적 의미왜곡 방지 |
| `standard_korean` | 변환 결과물이 문법적으로 자연스러운 표준 한국어인가 | 의료진 가독성 및 후속 파싱 안정성 확보 |
| `added_fact` | **[False 강제]** 원문에 없던 증상, 시점, 정도가 추가되었는가 | LLM의 자의적 과잉 임상 판단(환각) 차단 |
| `omitted_fact` | **[False 강제]** 원문에 있던 통증 정도나 부정 맥락이 빠졌는가 | **중증 위험 단서의 치명적 소실 방어** |

---

## 6. 현행 요약 지표 기준 (`reports/summary.json`)

| 정량 평가 지표 | 도출 결괏값 | 엔지니어링 지표 해석 |
| --- | ---: | --- |
| **평가 케이스 총합** | 200건 | 스타터 검증셋 전체 풀 커버리지 실행 |
| **추론 및 Judge 모델**| `amazon.nova-lite-v1:0` | 초저지연 경량 모델 기준의 보수적 검증 환경 |
| **최종 의미 성공률** | **0.900** (90.0%) | 4대 엄격 조건을 완벽하게 통과한 파이프라인 신뢰도 |
| **동일 의미 판정률** | **0.925** (92.5%) | 임상적 뉘앙스와 환자 호소 의도가 일치한 비중 |
| **표준어 문법 판정률**| **0.990** (99.0%) | 구어체가 완벽한 문장형 데이터로 정제된 비중 |
| **정보 임의 추가 없음**| **0.965** (96.5%) | 없는 병명을 지어내지 않는 환각 억제력 |
| **정보 임의 누락 없음**| **0.930** (93.0%) | 환자의 핵심 발화를 빠뜨리지 않는 데이터 보존율 |
| **평균 RAG 힌트 매칭수**| 0.275개 | 일반어 발화 시 불필요한 RAG 개입을 스킵하는 동적 라우팅 효율 |

---

## 7. 실패 유형 집중 분석 (`reports/failed_cases.csv`)

집계된 20건의 실패 파티션 분포입니다. 단일 발화에서 복합 오류 발생 시 시스템은 우선순위(`added` $\rightarrow$ `omitted` $\rightarrow$ `mismatch` $\rightarrow$ `not_standard`)에 의해 대표 실패 코드를 바인딩합니다.

* `omitted_fact` (10건): 구어체 뉘앙스 축약 중 통증의 강도 표현 일부 누락
* `added_fact` (7건): 모호한 문장을 매끄럽게 잇는 과정에서 시점 단서 일부 과생성
* `not_standard_korean` (2건) / `meaning_mismatch` (1건)

### 💡 핵심 실패 사례 심층 교훈 (`dialect_norm_002`)
* **환자 Raw 발화:** *"사래가 자주 걸려요"*
* **LLM 오답 생성:** *"콧물이 자주 나요"* $\rightarrow$ 판정: `meaning_mismatch` (실패)

> **엔지니어링 아키텍처 관점의 타당성:** > 고령층이 호소하는 '사래' 표현을 경량 LLM이 호흡기 일반 증상인 '콧물'로 치환하려다 포착된 사례입니다. 이는 **단순히 문장을 매끄럽게 만드는 것보다 환자 언어의 임상적 원의를 지키는 것이 훨씬 중요하다**는 대원칙을 입증합니다. 본 평가 프레임워크가 이러한 1%의 치명적 의미 왜곡을 사전에 걸러냄으로써, 운영 환경에서는 모호한 단어를 억지로 표준화하지 않고 원문 그대로 의사에게 전달하는 안전망이 가동됩니다.

---

## 8. 벤치마크 CLI 구동 가이드

```bash
cd munjin-talk-talk

export AWS_PROFILE=<your-profile>
export AWS_REGION=ap-northeast-2
export DIALECT_SEMANTIC_MODEL_ID=apac.amazon.nova-lite-v1:0
export DIALECT_SEMANTIC_JUDGE_MODEL_ID=apac.amazon.nova-lite-v1:0

pip install -r backend/serverless/src/requirements.txt

# 전체 200건 풀 벤치마크 실행
python evaluation/dialect_rag/run_dialect_semantic_eval.py \
  --input evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl \
  --output-dir evaluation/dialect_rag/reports/run_latest
```

*(고속 스모크 테스트 시에는 끝에 `--limit 20` 플래그를 할당하여 상위 20건만 파이프라인을 관통시킵니다.)*

---

## 9. Git 형상 관리 거버넌스

| 구분 | 통제 대상 경로 | 형상 관리 사상 |
| :---: | --- | --- |
| **커밋 확정 대상** | `README.md`<br>`run_dialect_semantic_eval.py`<br>`data/dialect_norm_eval_200.*`<br>`reports/summary.json`<br>`reports/failed_cases.csv` | 재현 가능한 시드 데이터셋과 최종 지표 스냅샷은 프로젝트 마스터 아티팩트로 영구 트래킹합니다. |
| **커밋 차단 대상** | `reports/run_latest/`<br>`*_case_results.jsonl`<br>Bedrock Raw Trace 로그 | Bedrock Judge의 확률적 변동성이 섞인 대량 런타임 중간 로그는 레포지토리에 적재하지 않습니다. |
