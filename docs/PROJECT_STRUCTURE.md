# 문진톡톡 MVP 코드베이스 구조 및 모듈 책임 명세서

본 문서는 문진톡톡 MVP 프로젝트에 온보딩하는 엔지니어 및 아키텍처를 검토하는 해커톤 심사위원이 **프로젝트의 폴더 토폴로지와 핵심 소스 파일별 비즈니스 책임을 직관적으로 파악할 수 있도록 작성된 디렉터리 매뉴얼**입니다.

저장소는 실제 MVP 배포에 필요한 프로덕션 코드와 문서만 남기는 것을 목표로 엄격히 정제되어 있습니다. 로컬 IR 벤치마크 산출물, 페르소나 시뮬레이션 결과, 임시 빌드 아티팩트는 프로덕션 레포지토리에 커밋하지 않는 것을 대원칙으로 합니다.

---

## 1. 최상위 루트 레이아웃

```text
munjin-talk-talk/
├── README.md
├── amplify.yml
├── frontend/
├── backend/
└── docs/
```

| 경로 | 역할 및 비즈니스 책임 |
| --- | --- |
| `README.md` | 프로젝트 총괄 소개 및 End-to-End 서비스 UX 입구 문서 |
| `amplify.yml` | AWS Amplify Hosting 기반의 프론트엔드 CI/CD 빌드 명세서 |
| `frontend/` | React 18 + Vite 기반의 단일 페이지 웹 애플리케이션(SPA) |
| `backend/` | AWS SAM 기반의 완전 관리형 서버리스 백엔드 인프라 |
| `docs/` | AI 파이프라인, 데이터 스키마, 클라우드 배포, 데이터 보안 매뉴얼 |

---

## 2. 프론트엔드 아키텍처 (`frontend/`)

```text
frontend/
├── package.json / package-lock.json
├── index.html / vite.config.js / .env.example
└── src/
    ├── App.jsx
    ├── main.jsx
    ├── components/
    │   ├── staff/              # 접수처 파트
    │   ├── patient/            # 환자 키오스크 파트
    │   ├── doctor/             # 의료진 대기열 & 원페이퍼 파트
    │   └── tablet/             # 공통 UI 모듈
    ├── hooks/
    ├── services/
    │   └── api/
    ├── config/
    ├── assets/
    └── styles/
```

### `src/App.jsx`
SPA의 최상위 라우터이자 글로벌 세션 상태 컨트롤러입니다.
* **라우팅 책임:** `/staff`, `/patient/:sessionId`, `/doctor/queue`, `/doctor/:sessionId`, `/guide/:sessionId`
* **제어 책임:** 상단 내비게이션 바 활성화 제어 및 접수 대기열 목록 백그라운드 폴링(Polling)

### `components/staff/` (접수처 도메인)
```text
ReceptionView.jsx          # 접수처 화면 메인 뷰 컨트롤러
ReceptionForm.jsx          # 환자 메타데이터 입력 및 초/재진 선택 폼
ReceptionSessionList.jsx   # 금일 생성된 접수 대기열 리스트 뷰
ReceptionManualInput.jsx   # 현장 직원 수동 문진 기입 폼
receptionUtils.js          # 연락처 마스킹, 만 나이 계산 헬퍼 유틸리티
```

### `components/patient/` (환자 키오스크 도메인)
```text
PatientKioskView.jsx       # sessionId 기반 세션 로딩 및 진입 래퍼
PatientFlow.jsx            # 환자 음성 문진 단계 전이 스테이트 머신(State Machine)
VisitTypeScreen.jsx        # 초진/재진 최종 확인 스크린
VoiceScreen.jsx            # 실시간 STT 전사 텍스트 렌더링 및 음성 입력 UI
ConfirmTranscriptScreen.jsx# 음성 인식 결과 검토 및 수정 스크린
SafetyAlertScreen.jsx      # 중증 위험 표현 감지 시 직원 도움 호출 전환 뷰
StaffCallScreen.jsx        # 직원 수동 호출 후 대기 안심 스크린
DoneScreen.jsx             # 문진 완료 안내 및 대기열 복귀 스크린
PatientGuideScreen.jsx     # 최종 환자 안내문 렌더링 및 인쇄 전용 뷰
```

### `components/doctor/` (의료진 진료 도메인)
```text
DoctorQueueView.jsx        # 의료진 외래 진료 대기열 폴링 뷰
DoctorView.jsx             # 원페이퍼 세션 패치 및 로딩 상태 래퍼
DoctorOnePager.jsx         # 검증된 정제 원페이퍼 본문 UI
DoctorOnePagerParts.jsx    # 증상 카드, 인용구 하이라이트, 문맥 Chip 조각 모음
DoctorAgendaPanel.jsx      # 환자 질문 대조, 의사 답변 기입, 안내문 강조어 선택 폼
```

### `hooks/useStreamingTranscribe.js`
Amazon Transcribe Streaming 웹소켓 통신을 React 생명주기에 동기화한 커스텀 훅입니다.
* **상태 캡슐화:** 녹음 활성 여부, 실시간 Partial 텍스트, 확정 Final 버퍼, 에러 핸들링, 세션 경과 시간 측정

### `services/` (통신 및 인터페이스 계층)
* `api/client.js`: HTTP Fetch 인터셉터, 세션 토큰 헤더 병합, 기본 URL 바인딩
* `api/sessions.js` / `transcripts.js` / `doctor.js`: 도메인별 REST API 호출 모듈화
* `transcribeStreaming.js`: 브라우저 마이크 PCM 전송용 웹소켓 클라이언트 구현체
* `onepagerAdapter.js`: 백엔드 원페이퍼 JSON 스키마를 프론트엔드 UI 렌더링 규격으로 매핑하는 어댑터

---

## 3. 서버리스 백엔드 아키텍처 (`backend/serverless/src/`)

```text
backend/serverless/src/
├── handler.py / settings.py / security.py / utils.py
├── sessions.py / artifact_store.py / artifact_policy.py / privacy.py
├── audio.py / llm.py / langchain_prompting.py
├── orchestration.py / pipeline_graph.py / pipeline_nodes.py
├── pipeline_state.py / pipeline_trace.py
├── dialect_config.py / dialect_rag.py / dialect_normalization.py
├── rag_context.py / extraction_prompts.py / extraction_schema.py
├── retrieval.py / retrieval_documents.py / retrieval_embeddings.py / retrieval_scoring.py
├── clinical_terms.py / clinical_state.py / domain_config.py / question_sets.py
├── onepager.py / onepager_sections.py / onepager_review.py / guide.py
├── schemas/
└── data/
```

백엔드는 단일 거대 소스 코드를 탈피하여, 책임에 따라 **5개의 독립 엔지니어링 레이어**로 분리되어 있습니다.

### 1) API 및 보안 인증 계층
* `handler.py`: Lambda 진입점(Entrypoint). API Gateway HTTP 라우터 매핑
* `settings.py`: 런타임 환경 변수, AWS SDK 클라이언트 인스턴스, 모델 ID 로더
* `security.py`: 현장 직원/의사 접근 코드 대조, HMAC 서명 JWT 발급, 환자 세션 토큰 검증

### 2) 데이터 최소화 및 스토리지 계층
* `sessions.py`: DynamoDB 세션 테이블 최소 상태값 CRUD 및 대기열 제어
* `artifact_store.py`: S3 아티팩트 버킷 Object Key 생성 및 비식별 입출력 인터페이스
* `artifact_policy.py`: S3 적재 직전 파일별 운영 산출물 필드 비식별화(Sanitization) 강제
* `privacy.py`: 접수 메타데이터 정규화 및 정규표현식 기반 PII 마스킹 유틸리티

### 3) LangGraph 오케스트레이션 계층
* `orchestration.py`: Q1~Q4 답변 수합, 백그라운드 Lambda 비동기 호출 트리거, 재분석 진입점
* `pipeline_graph.py`: LangGraph 노드 연결 토폴로지 및 조건부 전이 에지(Edge) 컴파일러
* `pipeline_nodes.py`: 추론 파이프라인의 개별 연산을 수행하는 비즈니스 노드 함수 11종 탑재
* `pipeline_state.py`: 그래프 노드 간 오염 없이 공유되는 TypedDict 상태 계약서
* `pipeline_trace.py`: 시스템 추론 판단의 결정 근거를 수집하는 감사 전용 텔레메트리

> **💡 관심사의 분리(SoC) 설계 사상:** > `pipeline_graph.py`는 전체 워크플로우의 **'지형도'** 만 명기하고, 실제 API 연산은 `pipeline_nodes.py`에 격리했습니다. 이를 통해 파이프라인의 실행 순서 변경과 노드 내부의 LLM 프롬프트 튜닝이 서로의 코드에 Side-effect를 주지 않고 독립적으로 수행됩니다.

### 4) 추론 및 매칭 엔진 계층
* `llm.py` / `langchain_prompting.py`: Bedrock Runtime 호출 및 LangChain 파서 인터페이스
* `extraction_prompts.py` / `extraction_schema.py`: 문항별 Bedrock 프롬프트 동적 라우팅 및 Grounding 검증기
* `retrieval.py` / `retrieval_scoring.py`: BM25 + Vector + Label 스코어링 융합 기반의 Hybrid IR 메인 모듈
* `clinical_state.py`: 추출된 증상 스팬을 활성(Active) vs 비활성(Inactive: 부재/호전)으로 분류하는 필터 엔진

### 5) 도메인 산출물 빌더 계층
* `onepager.py` / `onepager_sections.py`: 최종 의료진 화면 JSON 조립기
* `onepager_review.py`: Bedrock Nova Pro 기반의 필수 확인 항목 및 EMR 초안 문장 검토기
* `guide.py`: 의사 소견 입력 데이터의 S3 적재 및 고령 환자 맞춤형 쉬운 안내문 생성기

---

## 4. 정적 도메인 데이터 자산 (`src/data/`)

```text
src/data/
├── domain_packs/respiratory.json    # 호흡기 슬롯 규격, 규칙 사전, 응급 플래그 트리거
├── question_sets/default.json       # Q1~Q4 질문 명세 마스터
└── (비공개 배치 주입 3종)            # 질병백과 본문 / 증상 인덱스 / 벡터 임베딩 캐시
```
*(주의: `symptom_retrieval_dataset` 등 LLM이 임시로 생성한 데이터셋은 파이프라인 정적 의존성으로 사용하지 않습니다. 도메인 확장 시에는 정제된 백과 원천 데이터 주입과 공개 팩(Pack) 추가가 동기화되어야 합니다.)*

---

## 5. 요구사항 변경에 따른 소스 네비게이션 가이드

프로젝트 요구사항을 변경할 때 타깃으로 잡아야 하는 골든 매트릭스입니다.

| 수정하려는 비즈니스 요구사항 | 우선적으로 수정할 핵심 타깃 경로 |
| --- | --- |
| **REST API 엔드포인트 신규 등록** | `backend/serverless/src/handler.py` |
| **백엔드 인프라 환경 변수 추가** | `template.yaml` 및 `src/settings.py` |
| **환자 태블릿 문진 문구 변경** | 백엔드 `data/question_sets/default.json`<br>프론트엔드 오프라인 팩 `src/config/questions.js` |
| **Amazon Bedrock 프롬프트 수정**| `extraction_prompts.py`, `onepager_review.py`, `guide.py` |
| **강원 방언 사전 및 사투리 RAG 수정**| `dialect_config.py`, `dialect_rag.py`, `data/dialect_packs/` |
| **의학 백과 RAG 참고 문맥 범위 변경**| `rag_context.py`, `retrieval_documents.py`, `clinical_terms.py` |
| **LLM 입출력 JSON 스키마 변경** | `schemas/extraction.py`, `review.py`, `guide.py` |
| **Grounding 원문 대조 로직 수정** | `extraction_schema.py` 및 `schemas/extraction.py` |
| **LangGraph 분석 단계 노드 추가** | `pipeline_state.py` $\rightarrow$ `nodes.py` $\rightarrow$ `graph.py` |
| **Hybrid IR 검색 가중치 점수 튜닝** | `retrieval_scoring.py` 및 `settings.py` |
| **원페이퍼 화면 컴포넌트 퍼블리싱**| `frontend/src/components/doctor/DoctorOnePager.jsx` |
| **인쇄용 환자 안내문 레이아웃 수정**| `PatientGuideScreen.jsx` 및 `PatientGuideScreen.css` |
| **저장 데이터 정책 및 비식별 검증**| `tests/test_schema_and_artifact_policy.py` |

---

## 6. 형상 관리 제외 대상 (`.gitignore` 통제)

보안 규정 및 빌드 무결성을 위해 다음의 경로들은 원격 저장소 커밋을 엄격히 차단합니다.

```text
# 프론트엔드 빌드 산출물 및 의존성
frontend/node_modules/
frontend/dist/
frontend/.env*

# 백엔드 로컬 SAM 인프라 스태킹
backend/serverless/.aws-sam/
backend/serverless/samconfig.toml

# 민감 비공개 런타임 데이터 및 캐시
backend/serverless/src/data/diseases_cleaned.json
backend/serverless/src/data/symptom_index.json
backend/serverless/src/data/symptom_embeddings_*.json
backend/serverless/src/__pycache__/
outputs/
```
