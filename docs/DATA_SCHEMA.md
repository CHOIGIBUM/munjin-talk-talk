# 문진톡톡 내부 JSON 스키마

이 문서는 DynamoDB에 저장되는 문진 세션과, LLM/IR/원페이퍼 단계에서 오가는 핵심 JSON을 정리합니다.

## 1. Session Item

DynamoDB `MunjinSessions` 테이블의 기본 단위입니다.

```json
{
  "session_id": "s_1780...",
  "created_at": "2026-06-01T10:00:00+09:00",
  "updated_at": "2026-06-01T10:04:20+09:00",
  "status": "doctor_ready",
  "queue_number": 3,
  "visit_type": "initial",
  "patient": {
    "name": "김*자",
    "birth_date": "1950-09-17",
    "age": 75,
    "sex": "여성",
    "department": "이비인후과",
    "doctor": "이민우",
    "phone": "010-0000-0000"
  },
  "responses": {},
  "extractions": {},
  "matched_symptoms": [],
  "onepager": {},
  "patient_guide": {}
}
```

## 2. Response

환자 태블릿 또는 직원 직접 입력으로 저장되는 문항별 원문입니다.

```json
{
  "Q1": {
    "text": "어제부터 목이 칼칼하고 코가 막혀요",
    "confirmed": true,
    "input_method": "transcribe_streaming",
    "created_at": "2026-06-01T10:01:00+09:00"
  }
}
```

## 3. Extraction

Bedrock이 환자 원문을 의미 단위로 나눈 결과입니다. 이 JSON은 `schemas/extraction.py`의 Pydantic fixed schema를 통과해야 저장됩니다. `source_quote`는 반드시 원문에 실제로 존재해야 합니다.

```json
{
  "question_id": "Q1",
  "method": "bedrock",
  "validator_passed": true,
  "normalized_utterance": "어제부터 목이 칼칼하고 코가 막힘",
  "spans": [
    {
      "type": "symptom",
      "slot_ref": "throat_irritation",
      "name": "목 불편감",
      "normalized_text": "목 자극",
      "source_quote": "목이 칼칼",
      "status": "있음",
      "explain": "목의 자극감을 직접 표현함"
    }
  ],
  "clinical_clues": [
    {
      "category": "증상맥락",
      "label": "시작시점",
      "summary": "어제부터 증상 시작",
      "source_quote": "어제부터",
      "priority": "일반",
      "related_symptoms": ["목 불편감"]
    }
  ],
  "questions": []
}
```

## 4. Matched Symptom

LLM span을 표준 증상 인덱스와 BM25 + Titan vector로 매칭한 결과입니다.

```json
{
  "slot_id": "throat_irritation",
  "name": "목의 통증",
  "score": 0.9,
  "source_quote": "목이 칼칼",
  "normalized_text": "목 자극",
  "status": "있음",
  "ir_method": "bm25_titan_hybrid",
  "ir_trace": {
    "bm25_score": 0.72,
    "vector_score": 0.28,
    "label_score": 0.9,
    "accept_reason": "vector_plus_lexical_or_label",
    "top_candidates": []
  }
}
```

### Extraction validation error

Pydantic 검증에 실패하면 저장하지 않고 retry prompt로 넘길 오류 배열을 만듭니다.

```json
[
  {
    "field": "spans.0.score",
    "type": "extra_forbidden",
    "message": "Extra inputs are not permitted"
  },
  {
    "field": "spans.0.source_quote",
    "type": "value_error",
    "message": "quote must be an exact substring of the patient answer"
  }
]
```

## 5. Onepaper

의사용 화면이 읽는 최종 JSON입니다.

```json
{
  "patient_summary": {
    "display_name": "김*자",
    "age_text": "75세",
    "sex": "여성",
    "department": "이비인후과",
    "visit_type": "initial"
  },
  "symptom_slots": [],
  "clinical_clues": [],
  "agenda": [
    {
      "category": "복약질문",
      "summary": "처방약과 영양제 병용 가능 여부 문의",
      "original_quote": "영양제 같이 먹어도 되나요",
      "source_question": "Q4"
    }
  ],
  "doctor_brief": {
    "headline": "증상: 목의 통증 / 질문: 처방약과 영양제 병용 문의",
    "priority": "일반",
    "sections": []
  },
  "review_items": [
    {
      "text": "발열 여부와 실제 체온 확인",
      "priority": "일반",
      "evidence": "목이 칼칼하고 코가 막힘"
    }
  ],
  "transfer_text": "75세 여성 초진 환자. 어제부터 목 불편감과 코막힘 호소.",
  "safety_flags": []
}
```

## 6. Patient Guide

의사가 작성한 답변과 강조사항을 환자 안내문 화면에 보여주는 JSON입니다.

```json
{
  "patient_name": "김*자",
  "items": [
    {
      "question": "영양제 같이 먹어도 되나요?",
      "answer": "진료실에서 안내받은 내용을 따라 주세요.",
      "tts_text": "진료실에서 안내받은 내용을 따라 주세요."
    }
  ],
  "doctor_instruction": "약이랑 영양제 같이 꼭 아침 저녁으로 드세요."
}
```

## 데이터 원칙

- 환자 원문은 `responses.Qx.text`에 보존합니다.
- LLM 추출 결과는 Pydantic fixed schema, enum, 추가 필드 금지, `source_quote` 원문 근거 검증을 모두 통과해야 합니다.
- LLM 추출 JSON에는 `score`, `confidence`, `probability` 같은 임의 수치를 저장하지 않습니다. 이런 필드가 들어오면 `extra_forbidden` 검증 오류로 재시도됩니다.
- 원페이퍼 review LLM과 환자 안내문 LLM 출력도 각각 `schemas/review.py`, `schemas/guide.py`의 Pydantic schema를 통과해야 합니다.
- 증상 매칭은 LLM 후보만 믿지 않고, 원천 JSON 기반 IR 후보와 교차 검증합니다.
- 원페이퍼의 증상 `score`는 LLM이 만든 값이 아니라 BM25, Titan vector, 표준명 직접 유사도로 계산한 IR 매칭 점수입니다.
- rule-based 추출은 기본 운영 경로가 아니며 `ALLOW_RULE_FALLBACK=true`일 때만 사용합니다.
- 환자 안내 강조사항은 의사가 입력한 문구를 그대로 보여주는 것이 기본입니다.
