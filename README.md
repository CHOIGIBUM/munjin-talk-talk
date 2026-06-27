# 문진톡톡 사투리 RAG 의미 보존 평가 브랜치

본 브랜치(`eval/dialect-rag`)는 문진톡톡 공식 서비스 코드와 분리되어, **사투리 RAG(Retrieval-Augmented Generation) 파이프라인의 '의미적 무결성(Semantic Integrity)'을 정량적으로 검증하기 위한 탐색적 실험(Exploratory Evaluation) 환경**입니다.

공식 서비스 아키텍처 및 메인 실행 코드는 [main 브랜치](https://github.com/X-AI-KNU/munjin-talk-talk/tree/main)를 기준으로 합니다. 본 브랜치는 해커톤 심사 및 기술 검토 과정에서 **"사투리를 표준어로 치환할 때 원문 데이터의 왜곡이나 손실이 발생하지 않는가?"** 에 대한 엔지니어링 검증 근거를 투명하게 제공하기 위해 별도 구축되었습니다.

---

## 1. 벤치마크 핵심 목적 (Core Evaluation Question)

고령 환자는 문진 과정에서 강원 방언, 구어체, 지역 특유의 비정형 표현을 빈번하게 사용합니다. 문진톡톡의 사투리 RAG는 이러한 표현을 마주했을 때 즉시 진단명으로 단정 짓지 않고, 강원 방언팩에서 매칭된 어휘 힌트를 Bedrock 표준어 변환 프롬프트에 '참고 정보'로만 제한하여 주입합니다.

따라서 본 브랜치에서 입증하고자 하는 단 하나의 핵심 검증 명세는 다음과 같습니다.

> **임상적 의미 보존 검증 (Clinical Semantic Preservation)**
> 사투리 및 구어체 문진 답변을 표준어 보조 문장으로 치환했을 때, 환자가 발화한 **[증상명, 부정 맥락, 시점, 정도, 복약 사실, 질문 의도]**가 임의로 추가(Hallucination)되거나 누락(Omission)되지 않고 100% 보존되는가?

---

## 2. 참조 아티팩트 색인

본 브랜치에 수록된 평가 파이프라인 및 지표 산출물입니다.

| 문서 / 파일 링크 | 포함 내용 및 임상적 역할 |
| --- | --- |
| **[평가 프레임워크 명세](evaluation/dialect_rag/README.md)** | 평가 목적, 데이터 스키마, CLI 실행 방법, 지표 해석 가이드 |
| **[공식 요약 지표](evaluation/dialect_rag/reports/summary.json)** | 200개 검증 케이스 기준 핵심 정량 지표 스냅샷 |
| **[실패 케이스 덤프](evaluation/dialect_rag/reports/failed_cases.csv)** | 의미 불일치, 정보 임의 추가/누락 등 취약 패턴 집중 분석 인벤토리 |
| **[평가 데이터셋](evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl)** | 사투리/구어체 입력 Raw 발화와 임상 기준 표준어(Gold Standard) 매핑 |
| **[평가 실행 스크립트](evaluation/dialect_rag/run_dialect_semantic_eval.py)** | RAG 힌트 검색 → Bedrock 생성 → Judge 교차 검증 자동화 러너 |
| **[방언팩 런타임 가이드](backend/serverless/src/data/README.md)** | `dialect_kangwon.json`의 파이프라인 내 역할 및 주입 방법론 |
| **[강원 방언팩 JSON](backend/serverless/src/data/dialect_packs/dialect_kangwon.json)** | 실제 RAG 검색에 사용되는 강원 방언 어휘/힌트 데이터 |

---

## 3. 평가 파이프라인 시퀀스

평가 스크립트는 백엔드 내부의 `retrieve_dialect_context()` 함수를 직접 호출하여 실제 프로덕션과 동일한 제약 조건 하에서 구동됩니다.

```text
[Step 01] 평가 입력 패치      ──> 사투리/구어체 환자 원문 텍스트 주입
[Step 02] 로컬 방언 RAG 검색 ──> dialect_kangwon.json에서 어휘 힌트(prompt_note) 추출
[Step 03] 표준어 생성 추론    ──> Bedrock Nova Lite 구동 (원문 팩트 추가/누락 금지 제약 강제)
[Step 04] 의미 보존 LLM Judge ──> Nova Lite Judge가 [원문 vs 정답 vs 생성문] 삼자 교차 대조
[Step 05] 아티팩트 최종 집계  ──> summary.json 및 failed_cases.csv로 리포팅
```

---

## 4. 엄격한 성공 판정 매트릭스

단일 테스트 케이스는 아래 4대 평가 지표를 단 하나도 누락 없이 100% 충족(AND 연산)해야만 최종 성공(`ok`)으로 확정됩니다.

```
Semantic Success = same_meaning ∧ standard_korean ∧ ¬added_fact ∧ ¬omitted_fact
```

| 평가 지표명 | 판정 기준 명세 | 임상적 방어 목표 |
|---|---|---|
| `same_meaning` | 원문의 핵심 증상, 시점 변화, 복약 사실이 유지되었는가 | 문진 데이터의 본질적 의미왜곡 방지 |
| `standard_korean` | 변환 결과물이 문법적으로 자연스러운 표준 한국어인가 | 의료진 가독성 및 후속 파싱 안정성 확보 |
| `added_fact` | **[False 강제]** 원문에 없던 증상, 시점, 정도가 추가되었는가 | LLM의 자의적 과잉 임상 판단(환각) 차단 |
| `omitted_fact` | **[False 강제]** 원문에 있던 통증 정도나 부정 맥락이 빠졌는가 | 중증 위험 단서의 치명적 소실 방어 |
