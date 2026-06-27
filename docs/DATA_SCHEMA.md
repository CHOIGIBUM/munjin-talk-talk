# 문진톡톡 데이터 규격 및 JSON 스키마 명세

본 문서는 문진톡톡 MVP의 백엔드 파이프라인, 데이터베이스, 스토리지 간에 교환되는 핵심 JSON 데이터 구조를 정의합니다.

시스템의 가장 중요한 데이터 설계 원칙은 다음과 같습니다.

> **결정론적 스키마 바인딩 (Deterministic Schema Binding)** >
> 모든 JSON 규격은 애플리케이션 코드에 사전에 고정(Hard-coded)되어 있으며, LLM은 자율적인 구조 생성자(Designer)가 아닌 **미리 준비된 슬롯의 값 충전자**(Value Populator)로만 기능합니다.

백엔드는 Pydantic 스키마를 통해 필드 존재 여부, 데이터 타입, 열거형(Enum) 제한, Extra Field 허용 여부, 그리고 `source_quote`의 원문 매칭률을 100% 검증합니다. 증상 슬롯 참조값(`slot_ref`), 힌트 alias, 안전 플래그 트리거는 도메인 규칙 자산(`domain_packs/respiratory.json`)에서 결정론적으로 주입됩니다.

또한, 데이터의 생명주기와 보안 등급에 따라 스토리지의 역할을 엄격히 분리합니다.

* **Amazon DynamoDB:** 세션 대기열, 상태값(Status), 초진/재진 여부, 최소한의 마스킹 환자 정보, S3 산출물 참조 포인터
* **Amazon S3:** PII(개인식별정보)가 비식별 처리된 분석 산출물(`*.redacted.json`) 및 감사 추적용 Trace 로그

---

## 🔄 전체 데이터 수집 및 변환 흐름

```text
POST /sessions
  └── [DynamoDB] 경량 세션 아이템(Minimal Session Item) 생성

POST /process-answers
  ├── 환자가 최종 확인한 Q1~Q4 텍스트 답변 일괄 수신
  ├── [S3] answers.redacted.json 원문 아카이빙
  ├── [DynamoDB] status -> `analysis_pending` 상태 전환
  ├── [Lambda 비동기 호출] LangGraph 분석 워크플로우 트리거
  │     ├── 문맥 표준화 → 의미 Span 추출 → Pydantic 스키마 검증 → Quote Grounding 검증
  │     └── Hybrid IR + Linker 매칭을 통한 `matched_slots` 확정
  ├── [S3] onepaper.redacted.json 원페이퍼 산출물 저장
  └── [DynamoDB] risk 등급, 최종 status, S3 Object Key 갱신

POST /doctor-response
  ├── 의사의 코멘트 수신 및 [S3] doctor_review.redacted.json 저장
  ├── 고령 환자 맞춤형 쉬운 안내문 생성 로직 구동
  ├── [S3] patient_guide.redacted.json 저장
  └── [DynamoDB] status -> `reviewed` 전환 및 guide_key 갱신

GET /onepager/{session_id}  ───> [S3] onepaper.redacted.json 실시간 패치
GET /guide/{session_id}     ───> [S3] patient_guide.redacted.json 실시간 패치
```

---

## 1. DynamoDB Session Item 규격

`MunjinSessions` 테이블에 레코딩되는 마스터 엔티티입니다.

* **Partition Key:** `session_id` (String)

```json
{
  "session_id": "s_1780379760_45542aeb",
  "created_at": "2026-06-08T01:20:00+00:00",
  "updated_at": "2026-06-08T01:25:10+00:00",
  "expires_at": 1781000000,
  "status": "completed",
  "queue_number": 3,
  "visit_type": "initial",
  "risk": "none",
  "patient": {
    "name": "김*자",
    "age": 75,
    "age_band": "70대",
    "gender": "여성",
    "department": "이비인후과",
    "doctor": "이민우",
    "receipt_id": "A-0427",
    "honorific": "어르신"
  },
  "artifact": {
    "bucket": "<artifact-bucket-name>",
    "prefix": "sessions/2026-06-08/s_1780379760_45542aeb/",
    "answers_key": "sessions/2026-06-08/s_1780379760_45542aeb/answers.redacted.json",
    "onepaper_key": "sessions/2026-06-08/s_1780379760_45542aeb/onepaper.redacted.json",
    "guide_key": "sessions/2026-06-08/s_1780379760_45542aeb/patient_guide.redacted.json",
    "consent_key": "sessions/2026-06-08/s_1780379760_45542aeb/consent.json",
    "trace_key": "sessions/2026-06-08/s_1780379760_45542aeb/llm_trace.redacted.json"
  },
  "question_status": {
    "Q1": {
      "answered": true,
      "span_count": 2,
      "matched_count": 2,
      "method": "bedrock_nova_pro",
      "has_safety_flag": false
    }
  },
  "onepager_ready": true,
  "guide_ready": false,
  "privacy_consent": {
    "accepted": true,
    "version": "munjin-privacy-consent-2026-06-07",
    "method": "patient_tablet_modal",
    "accepted_at": "2026-06-08T01:21:00+00:00",
    "recorded_at": "2026-06-08T01:21:00+00:00"
  }
}
```

> **구현 참고:** `privacy_consent.version`은 태블릿 UI가 전송한 문자열을 명시적으로 기록합니다. 페이로드에 해당 필드가 누락된 예외 케이스에 한해서만 백엔드 세션 핸들러가 기본값(`munjin-privacy-consent-v1`)을 할당합니다.

### 🛡️ DynamoDB 비저장 통제 대상

PII 오염 방지를 위해 다음의 필드들은 DynamoDB 테이블에 일절 기록하지 않습니다.

| 비저장 데이터 | 백엔드 처리 및 격리 방식 |
| --- | --- |
| **환자 실명** | `김*자` 형태의 단방향 마스킹 문자열로 변환 후 메모리 파기 |
| **정확한 생년월일** | 만 나이(`75`) 및 연령대(`70대`) 추출 직후 즉시 파기 |
| **원본 연락처** | MVP 데이터베이스 영구 저장 대상에서 원천 차단 |
| **문항별 발화 원문** | 비식별화 후 S3 `answers.redacted.json` 객체로 격리 |
| **LLM 중간 Spans 데이터** | 비식별화 후 S3 `answers.redacted.json` 객체로 격리 |
| **원페이퍼 전체 본문** | 비식별화 후 S3 `onepaper.redacted.json` 객체로 격리 |
| **의사 답변 전문** | 비식별화 후 S3 `doctor_review.redacted.json` 객체로 격리 |
| **LangGraph 노드 Trace** | 최소 추론 이벤트만 요약하여 S3 `llm_trace.redacted.json`으로 격리 |

---

## 2. S3 Artifact Object Layout

모든 산출물은 `sessions/YYYY-MM-DD/{session_id}/` 접두사(Prefix) 하위에 배치되며, 백엔드의 `artifact_store.py` 인터페이스를 통해서만 접근됩니다. (프론트엔드로 S3 Direct URL 노출 금지)

**S3 공통 봉투 규격(Envelope Wrapper):**

```json
{
  "stored_at": "2026-06-08T01:25:10+00:00",
  "schema_version": "munjin-artifact-v1",
  "payload": { ... }
}
```
*(기록되는 모든 `payload` 내부 데이터는 런타임에 `privacy.redact_payload()` 모듈을 통과하며, 전화번호·주민 등록 번호·이메일 패턴에 대한 정규식 영구 삭제가 선행됩니다.)*

---

## 3. 답변 및 분석 데이터 (`answers.redacted.json`)

```json
{
  "Q1": {
    "text": "어제부터 목이 칼칼하고 코가 막혀요.",
    "confirmed": true,
    "spans": [
      {
        "source_quote": "목이 칼칼하고",
        "type": "symptom",
        "slot_ref": "throat_irritation",
        "name": "목 자극감",
        "normalized_text": "목 자극감",
        "status": "있음",
        "alert": false,
        "explain": "환자가 목의 칼칼함을 직접 호소했습니다."
      }
    ],
    "structured": {
      "standardized_text": "어제부터 목이 칼칼하고 코가 막힙니다.",
      "clinical_clues": [],
      "questions": [],
      "unresolved_items": []
    },
    "matched_slots": [
      {
        "slot_id": "throat_irritation",
        "name": "목의 통증",
        "source_quote": "목이 칼칼하고",
        "span_type": "symptom",
        "alert": false,
        "normalized_text": "목 자극감",
        "status": "있음",
        "explain": "환자 표현을 아산백과 기반 증상 인덱스와 비교했고, 어휘 근거와 Titan 의미 벡터 근거가 함께 충족되어 표준 증상으로 매칭했습니다.",
        "ir_method": "bm25_titan_hybrid"
      }
    ]
  }
}
```

### 증상 상태 판단 및 매칭 통제 정책

발화 내에 특정 증상 단어가 포착되었다고 하여 모두 원페이퍼의 **'현재 불편함'** 카드로 렌더링되지 않습니다. 파이프라인은 `type`과 `status`를 조합하여 상태 주도형 라우팅을 수행합니다.

| 임상적 발화 상황 | `type` | `status` | 의료진 화면(Onepaper) 노출 영역 |
| --- | --- | :---: | --- |
| 현재 호소하는 활성 증상 | `symptom` 또는 `new` | `있음` | **[오늘 호소 증상 카드]** 에 등록 |
| 이전보다 악화된 증상 | `progress_worsened` | `있음` | **[오늘 호소 증상 카드]** + 악화 단서 하이라이트 |
| 이전과 상태가 비슷한 증상 | `progress_unchanged` | `있음` | **[오늘 호소 증상 카드]** 에 유지 |
| 현재 명시적으로 없다고 한 증상| `symptom_absent` | `없음` | 카드 노출 제외 $\rightarrow$ `clinical_clues(부재 단서)`로 격리 |
| 과거 증상이 호전된 상태 | `progress_improved` | `없음` | 카드 노출 제외 $\rightarrow$ `clinical_clues(호전 단서)`로 격리 |

> 💡 **아키텍처 통제 원리:** > `symptom_absent`와 `progress_improved` 속성을 가진 스팬은 **Hybrid IR 표준 증상 검색 파이프라인으로 진입하는 입구가 차단**됩니다. 
> 특히 `progress_improved`의 `status="없음"`은 임상적으로 질병이 100% 완치되었다는 의학적 선언이 아니라, **'오늘 의사가 진료실에서 집중적으로 파헤쳐야 할 핵심 주호소 카드 대상에서 제외한다'** 는 프론트엔드 라우팅 제어값입니다. 환자 원문이 완벽한 증상 소실을 명시하지 않았다면, 시스템은 "병이 완전히 나았다"는 허위 임상 사실을 생성하지 않고 문맥 단서로만 안전하게 보존합니다.

---

## 4. 의료진용 원페이퍼 (`onepaper.redacted.json`)

```json
{
  "patient_summary": {
    "display_name": "김*자",
    "age_text": "75세",
    "sex": "여성",
    "department": "이비인후과",
    "received_at": "10:30",
    "audio_duration_text": "확인중",
    "visit_type": "initial"
  },
  "symptom_slots": [],
  "clinical_clues": [],
  "agenda": [],
  "doctor_brief": {
    "headline": "",
    "sections": []
  },
  "review_items": [],
  "transfer_text": "",
  "safety_flags": [],
  "unresolved_items": []
}
```
*(참고: `review_items`, `doctor_brief`, `transfer_text` 필드는 LLM이 초안을 작성하지만, Pydantic 스키마 검증과 Source Quote 대조기가 유효성을 승인한 경우에만 빈 배열`[]`이 데이터로 치환됩니다.)*

---

## 5. 의사 답변 기록 (`doctor_review.redacted.json`)

```json
{
  "answers": [
    {
      "question_id": "Q4-1",
      "question_summary": "처방약과 영양제를 같이 먹어도 되는지 궁금함",
      "answer_text": "현재 영양제는 같이 드셔도 됩니다. 새 약이 추가되면 다시 확인해 주세요."
    }
  ],
  "patient_instruction": "증상이 심해지면 즉시 병원에 다시 와주세요.",
  "additional_notes": "증상이 심해지면 즉시 병원에 다시 와주세요.",
  "reviewed_at": "2026-06-08T01:30:00+00:00"
}
```

---

## 6. 환자 안내문 (`patient_guide.redacted.json`)

```json
{
  "generated_at": "2026-06-08T01:31:00+00:00",
  "items": [
    {
      "question": "처방약과 영양제를 같이 먹어도 되는지 궁금함",
      "answer_simple": [
        "현재 드시는 영양제는 이번 약과 같이 드셔도 됩니다.",
        "다른 약이 추가되면 병원이나 약국에 다시 확인해 주세요."
      ],
      "tts_emphasis_words": ["다른 약", "다시 확인"]
    }
  ],
  "delivery_options": ["screen", "tts", "print"],
  "generation_method": "bedrock_nova_lite_grounded"
}
```

---

## 7. 시스템 감사 로그 (`llm_trace.redacted.json`)

LLM의 블랙박스 추론 과정을 규명하고 의료·법적 책임 소재를 대조하기 위한 비식별 감사 로그(Audit Trail)입니다. 프롬프트 전문, Raw Response 본문, 전체 그래프 정의체, IR 전체 후보 리스트는 스토리지 용량 및 보안상 기록하지 않습니다.

```json
{
  "Q1": {
    "graph": "munjin_langgraph_answer_pipeline",
    "version": "v2",
    "question_type": "chief_complaint",
    "active_path": [
      "input_transcript",
      "quick_safety_flag",
      "rag_context_retrieval",
      "semantic_extraction",
      "schema_quote_validation",
      "hybrid_ir_match",
      "session_validation_save",
      "onepaper_refresh",
      "response_payload"
    ],
    "events": [
      {
        "node": "semantic_extraction",
        "status": "generated",
        "at": "2026-06-08T01:25:00+00:00",
        "details": {
          "attempt": 1,
          "model_id": "apac.amazon.nova-pro-v1:0",
          "langchain_chain": "langchain_core_prompt_bedrock_json",
          "output_parser": "langchain_json_output_parser",
          "raw_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        }
      }
    ],
    "matched_count": 1,
    "span_count": 1
  }
}
```
*(주의: 이 Trace에 기록되는 내부 스코어는 환자에게 노출되는 'AI 확신도'가 아닙니다. 엔지니어와 임상가가 시스템의 검색 엔진 매칭 타당성을 사후 검사하기 위한 백엔드 내부 지표입니다.)*

---

## 8. 파이프라인 스키마 예외 응답 (HTTP 422)

재시도 루프(Bounded Retry)를 거치고도 LLM이 지정된 스키마 정합성을 충족하지 못할 경우, 서버는 데이터를 불완전 저장하는 대신 명시적인 예외를 던집니다.

```json
{
  "error": "semantic_extraction_failed",
  "message": "LLM schema/quote validation failed after bounded retries.",
  "details": {
    "attempts": 3,
    "retry_loop": "langgraph_schema_quote_repair",
    "validation_error_count": 1
  }
}
```
*(단, 예외 발생 발화 내에 `Safety Flag(응급 징후)`가 감지되어 있던 경우에 한해, 추출 실패 분기에서도 우회 경로`safety_guardrail_save`를 타서 원페이퍼 상단에 응급 알림을 강제 노출합니다.)*
