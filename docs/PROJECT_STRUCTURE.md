# 문진톡톡 MVP 구조 정리

이 문서는 현재 저장소를 처음 보는 개발자가 “어디를 보면 되는지” 빠르게 잡기 위한 구조 설명서입니다.
로컬 실험 산출물은 제외하고, 실제 MVP 배포와 실행에 필요한 코드 중심으로 정리했습니다.

## 전체 폴더

```text
munjin-talk-talk-mvp/
├── backend/
│   └── serverless/
│       ├── src/
│       │   ├── handler.py                 # API Gateway Lambda 진입점
│       │   ├── settings.py                # 환경 변수, 모델 ID, 리소스 이름
│       │   ├── sessions.py                # DynamoDB 문진 세션 저장/조회
│       │   ├── audio.py                   # Transcribe Streaming presigned URL
│       │   ├── llm.py                     # Bedrock 호출 공통 함수
│       │   ├── orchestration.py           # 답변 처리 파이프라인
│       │   ├── extraction.py              # LLM 추출 진입점
│       │   ├── extraction_prompts.py      # Q별 추출 프롬프트와 모델 라우팅
│       │   ├── extraction_schema.py       # Pydantic 검증 adapter
│       │   ├── extraction_fallback.py     # Bedrock 실패 시에만 허용 가능한 fallback
│       │   ├── schemas/
│       │   │   ├── extraction.py          # 문항 추출 fixed schema, enum, quote grounding
│       │   │   ├── review.py              # 원페이퍼 review LLM 출력 schema
│       │   │   └── guide.py               # 환자 안내문 LLM 출력 schema
│       │   ├── retrieval.py               # 증상 후보 검색/채택 판정
│       │   ├── retrieval_documents.py     # 원천 JSON을 IR 문서로 변환
│       │   ├── retrieval_embeddings.py    # Titan embedding 호출과 cache
│       │   ├── retrieval_scoring.py       # BM25, cosine, 직접 단어 가산점 계산
│       │   ├── clinical_terms.py          # 표준 증상/질환 JSON 로딩
│       │   ├── onepager.py                # 원페이퍼 생성/저장 진입점
│       │   ├── onepager_sections.py       # 원페이퍼 섹션 조립
│       │   ├── onepager_review.py         # Nova Pro 최종 리뷰/체크리스트 생성
│       │   ├── guide.py                   # 환자 안내문 생성
│       │   ├── utils.py                   # JSON/시간/텍스트 공통 도구
│       │   ├── common.py                  # 예전 import 호환용 facade
│       │   ├── requirements.txt           # Lambda Python 의존성
│       │   └── data/
│       │       ├── diseases_cleaned.json  # 아산병원 질환 원천 정제 데이터
│       │       └── symptom_index.json     # 표준 증상 인덱스
│       ├── template.yaml                  # AWS SAM 서버리스 인프라
│       └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── staff/                     # 접수처 화면
│   │   │   ├── patient/                   # 환자 태블릿 문진 화면
│   │   │   ├── doctor/                    # 의사 대기열/원페이퍼 화면
│   │   │   └── guide/                     # 환자 안내문 화면
│   │   ├── hooks/                         # React hook
│   │   ├── services/                      # API, streaming STT, onepager adapter
│   │   ├── data/                          # 화면용 질문/문구 데이터
│   │   ├── assets/                        # 로고/아이콘
│   │   └── styles/
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docs/
│   ├── PROJECT_STRUCTURE.md
│   ├── DATA_SCHEMA.md
│   ├── technical-guide.html               # 발표/공유용 HTML 설명서
│   └── DEPLOYMENT.md
├── amplify.yml                            # Amplify 프론트 빌드 설정
└── README.md
```

## 백엔드 실행 흐름

1. `handler.py`
   API Gateway 요청을 받아 `/sessions`, `/transcribe-stream-url`, `/process-answer` 같은 endpoint로 분기합니다.

2. `audio.py`
   환자 음성을 S3에 저장하지 않고, Amazon Transcribe Streaming WebSocket URL을 짧은 유효시간으로 발급합니다.

3. `orchestration.py`
   환자 답변 1개가 들어올 때마다 아래 순서로 처리합니다.

4. `extraction.py`
   Q별 난이도에 따라 Bedrock 모델을 고르고, `extraction_prompts.py`의 프롬프트로 고정 JSON을 요청합니다.

5. `schemas/extraction.py` + `extraction_schema.py`
   Pydantic으로 LLM 응답이 fixed schema, enum, 추가 필드 금지, `source_quote` 원문 근거 검증을 통과하는지 확인합니다. 실패하면 같은 답변을 다시 LLM에 보냅니다.

6. `retrieval.py`
   LLM이 뽑은 증상 후보를 `symptom_index.json` 기준 표준 증상으로 매칭합니다.
   점수는 vector similarity, BM25, 직접 표준 증상명/별칭 포함 여부를 합쳐 계산합니다.

7. `onepager.py`
   저장된 전체 답변, 추출 JSON, IR 결과를 조립해 의사용 원페이퍼 JSON을 만듭니다.

8. `onepager_review.py`
   Nova Pro가 의사 관점에서 체크리스트, EMR 초안, 누락/중복 위험을 검토합니다.

9. `guide.py`
   의사가 작성한 환자 안내 답변과 강조사항을 환자 안내문 JSON으로 변환합니다.

10. `sessions.py`
    모든 세션 상태, 원페이퍼, 안내문, 질문/답변 기록을 DynamoDB `MunjinSessions`에 저장합니다.

## 프론트엔드 실행 흐름

1. `components/staff/ReceptionView.jsx`
   접수처 화면의 controller입니다. 세션 생성, 목록 갱신, 직원 직접 입력 panel open/close만 관리합니다.

2. `components/staff/ReceptionForm.jsx`
   환자 이름, 생년월일, 성별, 초진/재진, 연락처 입력 UI입니다.

3. `components/staff/ReceptionSessionList.jsx`
   오늘 접수 목록과 태블릿/원페이퍼/안내문 이동 버튼을 렌더링합니다.

4. `components/staff/ReceptionManualInput.jsx`
   환자가 중단하거나 직원 도움이 필요한 경우 직원이 문진 답변을 직접 넣는 화면입니다.

5. `components/patient/PatientFlow.jsx`
   환자 태블릿 문진 흐름을 담당합니다. 질문 표시, 음성 녹음, streaming STT, 안전 flag 화면을 연결합니다.

6. `services/transcribeStreaming.js`
   브라우저 마이크 입력을 AWS EventStream 형식으로 변환해 Transcribe Streaming에 보냅니다.

7. `hooks/useStreamingTranscribe.js`
   환자 화면에서 사용할 수 있도록 streaming STT 상태를 React hook으로 감쌉니다.

8. `services/onepagerAdapter.js`
   백엔드 onepager JSON을 의사 UI가 기대하는 shape으로 정규화합니다.

9. `services/onepagerBrief.js`
   백엔드 `doctor_brief`가 비어 있을 때만 화면 fallback 요약을 만듭니다.

10. `components/doctor/DoctorOnePagerParts.jsx`
    원페이퍼의 아이콘, 단서 chip, 증상별 단서 연결 규칙을 모아 둔 보조 컴포넌트입니다.

## 핵심 JSON 데이터

### DynamoDB session

```json
{
  "session_id": "s_...",
  "patient": {
    "name": "김*자",
    "age": 75,
    "sex": "여성",
    "department": "이비인후과"
  },
  "visit_type": "initial",
  "responses": {
    "Q1": {
      "text": "어제부터 목이 칼칼해요",
      "confirmed": true,
      "created_at": "2026-06-01T..."
    }
  },
  "extractions": {
    "Q1": {
      "spans": [],
      "clinical_clues": []
    }
  },
  "matched_symptoms": [],
  "onepager": {},
  "patient_guide": {}
}
```

### LLM extraction

```json
{
  "normalized_utterance": "어제부터 목이 칼칼하다.",
  "spans": [
    {
      "slot_ref": "throat_irritation",
      "display_text": "목 불편감",
      "normalized_text": "목 자극",
      "source_quote": "목이 칼칼해요",
      "explain": "환자가 목의 자극감을 직접 표현함"
    }
  ],
  "clinical_clues": [
    {
      "category": "증상맥락",
      "label": "시작시점",
      "summary": "어제부터 증상 시작",
      "source_quote": "어제부터",
      "priority": "일반"
    }
  ],
  "questions": []
}
```

### Onepaper

```json
{
  "patient_summary": {},
  "symptom_slots": [],
  "clinical_clues": [],
  "agenda": [],
  "doctor_brief": {
    "headline": "증상: 목 불편감 / 질문: 약 복용 문의",
    "priority": "일반",
    "sections": []
  },
  "review_items": [],
  "transfer_text": "",
  "safety_flags": []
}
```

## 코드 분리 기준

- API endpoint는 `handler.py`에만 둡니다.
- AWS 리소스 접근은 `sessions.py`, `audio.py`, `llm.py`처럼 서비스별 파일로 제한합니다.
- LLM 프롬프트는 `*_prompts.py`에 두고, fixed schema는 `schemas/`, 검증 adapter는 `*_schema.py`에 둡니다.
- UI controller는 화면 상태만 관리하고, 렌더링 조각은 하위 component로 분리합니다.
- rule-based 코드는 `fallback` 이름이 들어간 파일에만 두고, 기본 경로에서는 Bedrock/validator 성공 데이터를 우선 사용합니다.

## 저장소에 포함하지 않는 것

- 로컬 IR 실험 산출물
- 100명 persona/evaluation 데이터
- `outputs/` 평가 결과
- `node_modules/`
- `dist/`
- AWS 임시 음성/전사 산출물
