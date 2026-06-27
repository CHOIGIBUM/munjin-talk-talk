# 문진톡톡 클라우드 프로덕션 배포 가이드 (AWS)

본 문서는 문진톡톡 MVP를 AWS 클라우드 환경에 프로비저닝하고 배포하는 표준 인프라 절차를 명세합니다. 대상 독자는 DevOps 배포 담당자, 백엔드 엔지니어, 그리고 아키텍처 재현성을 검토하는 해커톤 심사위원입니다.

시스템은 프론트엔드와 백엔드가 완전히 분리된 **디커플링(Decoupled) 서버리스 아키텍처**로 배포됩니다.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ [Frontend]  AWS Amplify Hosting (React 18 SPA)                         │
│ [Backend]   AWS SAM (API Gateway HTTP API + Lambda Python 3.12)        │
│ [Storage]   Amazon DynamoDB (Minimal State) + Amazon S3 (Redacted Key) │
│ [AI Engine] Transcribe Streaming + Bedrock (Nova Pro/Lite) + Titan     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 사전 준비 및 인프라 요구사항

### 🛠️ 필수 접근 권한
* AWS 계정 Root 또는 AdministratorAccess 상당의 IAM 권한
* GitHub 레포지토리 관리 권한 (Amplify 연동용)
* 로컬 터미널 내 `aws-cli` 및 `sam-cli` 인증 완료
* Amazon Bedrock 모델 액세스 유선/콘솔 활성화 완료

> **권장 리전(Region):** `ap-northeast-2` (아시아 태평양 - 서울) > 본 가이드의 모든 리소스 생성 및 CLI 명세는 서울 리전을 기준으로 작성되었습니다.

---

## 2. 전체 표준 배포 시퀀스

```text
[Step 01] S3 애플리케이션 아티팩트 버킷 생성
[Step 02] DynamoDB 세션 상태 테이블 (MunjinSessions) 생성
[Step 03] Lambda 실행 전용 IAM Role 및 Policy 프로비저닝
[Step 04] Amazon Bedrock 기반 모델 3종 사용 승인 확인
[Step 05] 백엔드 필수 런타임 데이터 주입 및 SAM 빌드/배포
[Step 06] 배포된 API Gateway Endpoint URL 확인
[Step 07] AWS Amplify 프론트엔드 호스팅 생성 및 Git 연동
[Step 08] Amplify 환경 변수(VITE_API_BASE_URL) 주입
[Step 09] SPA 라우팅용 Rewrite Rule 설정
[Step 10] End-to-End 인수 테스트 (Smoke Test)
```

### 🔐 백엔드 핵심 보안 파라미터

| 파라미터명 | 설명 및 용도 | 기본값 / 보안 권장사항 |
| --- | --- | --- |
| `StaffAccessToken` | 현장 접수 직원이 로그인 모달에 입력하는 접근 코드 | *(기존 호환성을 위해 변수명 유지)* |
| `DoctorAccessToken` | 진료실 의료진이 로그인 모달에 입력하는 접근 코드 | *(기존 호환성을 위해 변수명 유지)* |
| `AuthSigningSecret` | 세션 JWT 서명에 사용되는 HMAC 대칭키 Secret | **고엔트로피의 긴 난수 직접 기입 필수** |
| `AuthTokenTtlMinutes`| 발급된 세션 인증 토큰의 만료 시간(분) | `240` (4시간) |
| `CorsAllowOrigin` | 백엔드 API 호출을 허용할 프론트엔드 HTTPS 출처 | Amplify 배포 완료 도메인 지정 |
| `S3KmsKeyId` | S3 아티팩트 버킷의 SSE-KMS 암호화 키 ARN | *(비워둘 시 기본 SSE-S3 AES256 적용)* |

> ⚠️ **보안 원칙:** 접근 코드와 서명 대칭키는 절대 Git 커밋이나 프론트엔드 소스에 포함되지 않습니다. 프론트엔드는 코드를 저장하지 않으며, `/auth/login`을 통해 백엔드가 발급한 단기 토큰만 브라우저의 `sessionStorage`에 임시 보관합니다.

---

## 3. Step 01: S3 애플리케이션 아티팩트 버킷

환자의 문진 텍스트 산출물과 AI 추론 Trace를 비식별화하여 아카이빙하는 전용 버킷입니다. (음성 원본 파일 미저장)

**디렉터리 레이아웃:**
```text
sessions/YYYY-MM-DD/{session_id}/
  ├── consent.json
  ├── answers.redacted.json
  ├── onepaper.redacted.json
  ├── doctor_review.redacted.json
  ├── patient_guide.redacted.json
  └── llm_trace.redacted.json
```

* **필수 인프라 설정:** `Block Public Access 전체 활성화`, `기본 서버 측 암호화(SSE) 적용`, `Lifecycle Rule(3일 후 영구 삭제) 강제`, `Bucket Policy를 통한 Lambda IAM Role 단독 접근 통제`.

> ⚠️ **주의:** 본 버킷은 프론트엔드를 호스팅하는 'Amplify 버킷'이나 'SAM CLI 배포 스태킹 버킷'과 완전히 독립된 **서비스 데이터 전용 저장소**입니다.

---

## 4. Step 02: DynamoDB 세션 테이블

* **테이블명:** `MunjinSessions`
* **Partition Key:** `session_id` (String)
* **과금 및 보존 모드:** `On-Demand Capacity` 지정, `TTL 속성명: expires_at` 활성화

### 데이터 저장 경계 통제
DynamoDB는 초고속 상태 조회를 위한 메타데이터 허브로만 쓰입니다.

* **허용 속성:** `session_id`, `queue_number`, `status`, `visit_type`, `patient.name(김*자)`, `patient.age`, `patient.gender`, `patient.department`, `risk`, `artifact(S3 Key 목록)`
* **절대 금지 속성 (Zero-PII):** 환자 실명 원문, 생년월일 원문, 전화번호, 문항별 답변 원문, 원페이퍼 본문 전체, 의사 답변 텍스트 전문. *(해당 데이터는 S3 아티팩트에만 격리됨)*

---

## 5. Step 03: Lambda Execution IAM Role

Lambda 함수가 부여받아야 하는 최소 권한 명세입니다.

```text
[DynamoDB] dynamodb:GetItem, PutItem, UpdateItem, Scan  (대상: MunjinSessions ARN)
[S3]       s3:GetObject, PutObject                      (대상: 아티팩트 버킷 sessions/*)
[Bedrock]  bedrock:InvokeModel, InvokeModelWithResponseStream
[Transcribe] WebSocket Presigned URL 생성 권한
[CloudWatch] logs:CreateLogGroup, CreateLogStream, PutLogEvents
```
*(참고: 운영 보안을 위해 CloudWatch Logs의 데이터 보존 주기는 7~14일로 단축하고, 환자의 발화 원문 페이로드가 시스템 로그에 찍히지 않도록 핸들러 단에서 마스킹을 유지해야 합니다.)*

---

## 6. Step 04: Amazon Bedrock 모델 활성화

AWS 콘솔 `Amazon Bedrock -> Model access`에서 다음 3개 모델의 **Access Granted** 상태를 선행 확인합니다.

1. `Amazon Nova Pro` (심층 추론 및 원페이퍼 검증용)
2. `Amazon Nova Lite` (고속 데이터 포맷팅 및 안내문 생성용)
3. `Amazon Titan Text Embeddings v2` (Hybrid IR 벡터 추출용)

---

## 7. Step 05: SAM 백엔드 빌드 및 배포

### ⚠️ 필수 전제 조건
저작권 보호로 Git에서 제외된 **의학 백과 비공개 인덱스 3종**을 배포 직전 `src/data/` 폴더에 수동 주입해야 합니다.
* `diseases_cleaned.json` / `symptom_index.json` / `symptom_embeddings_*.json`

```powershell
cd backend/serverless
sam build
sam deploy --guided
```

**SAM 대화형 Deploy 입력 예시:**
```text
Stack Name: munjin-mvp-backend
AWS Region: ap-northeast-2
Parameter SessionsTableName: MunjinSessions
Parameter ArtifactsBucketName: <생성한_S3_버킷명>
Parameter LambdaRoleArn: <생성한_IAM_Role_ARN>
Parameter CustomVocabularyName:              <-- (공백 통과 시 Enter)
Parameter CorsAllowOrigin: https://main.<amplify-id>.amplifyapp.com
Parameter StaffAccessToken: <직원_접근코드>
Parameter DoctorAccessToken: <의료진_접근코드>
Parameter AuthSigningSecret: <고엔트로피_난수_Secret>
Confirm changes before deploy: y
Allow SAM CLI IAM role creation: n
MunjinApiFunction has no authentication. Is this okay?: y
```

배포 완료 후 터미널에 출력되는 `ApiEndpoint` 값을 복사합니다.

> 💡 **PowerShell 팁:** 파라미터 입력 시 공백으로 둘 항목(`CustomVocabularyName` 등)에 `""`를 입력하면 파싱 오류가 날 수 있으므로 가이드 모드에서 바로 Enter를 눌러 넘기십시오.

---

## 8. Step 07~08: AWS Amplify 프론트엔드 배포

AWS 콘솔 `AWS Amplify -> Hosting`에서 신규 앱을 연동합니다.

* **Git 연동:** `CHOIGIBUM/munjin-talk-talk-mvp` $\rightarrow$ `main` 브랜치 선택
* **Monorepo Root:** `frontend` 입력
* **빌드 설정:** 루트의 `amplify.yml` 자동 감지 확인 (빌드명령: `npm run build`, 산출물: `dist`)

### 호스팅 환경 변수 주입
```text
VITE_API_BASE_URL = https://<api-id>.execute-api.ap-northeast-2.amazonaws.com
AMPLIFY_MONOREPO_APP_ROOT = frontend
AMPLIFY_DIFF_DEPLOY = false
```

---

## 9. Step 09: SPA 라우팅 Rewrite 설정

React Router(SPA)의 새로고침 404 에러를 방지하기 위해 `Amplify Console -> Hosting -> Rewrites and redirects`에 규칙을 추가합니다.

```json
[
  {
    "source": "/<*>",
    "status": "404-200",
    "target": "/index.html"
  }
]
```

---

## 10. Step 10: 배포 인수 검증 (Smoke Test)

배포 직후 각 역할별 화면이 유기적으로 연결되는지 검증하는 시퀀스입니다.

1. **[직원 접수]** `/staff` 접속 $\rightarrow$ 접근 코드 로그인 $\rightarrow$ 환자 입력 및 문진 세션 생성 $\rightarrow$ DynamoDB 레코드 생성 및 실명 마스킹 확인
2. **[환자 문진]** `/patient` 대기열 접속 $\rightarrow$ 세션 선택 및 동의 $\rightarrow$ 음성 문진(Q1~Q4) 진행 $\rightarrow$ S3 내 `answers.redacted.json` 정상 적재 확인
3. **[의료진 원페이퍼]** `/doctor/queue` 접속 $\rightarrow$ '분석 완료' 확인 후 진입 $\rightarrow$ 원문 인용(Quote), 표준 증상 매칭, 확인 항목 렌더링 확인
4. **[안내문 발급]** 의사 소견 입력 후 저장 $\rightarrow$ `/guide/{id}` 렌더링 확인 및 인쇄(Print Layout) 테스트

---

## 11. 🛡️ 클라우드 보안 점검 체크리스트

- [ ] S3 아티팩트 버킷의 `Block Public Access`가 100% 활성화되어 있는가?
- [ ] S3 객체 자동 파기 주기가 `Lifecycle: 3 Days`로 정속 설정되어 있는가?
- [ ] DynamoDB 세션 테이블의 `TTL(expires_at)` 속성이 정상 작동 중인가?
- [ ] Lambda 함수 환경 변수에 접근 코드가 평문 노출되지 않고 안전하게 주입되었는가?
- [ ] API Gateway의 CORS 허용 출처가 와일드카드(`*`)가 아닌 정확한 Amplify 도메인인가?

---

## 12. 비용 최적화 체크리스트

해커톤 심사 기간 중 불필요한 클라우드 과금을 방지하기 위한 핵심 제어 항목입니다.

* **Bedrock 연산:** 분석 실패 시 무한 루프를 돌지 않도록 오케스트레이션의 `Bounded Retry(최대 3회)` 제한 유지
* **스토리지 누적:** S3 3일 파기 및 CloudWatch Logs 보존 주기(7일) 강제 적용 확인
* **DB IOPS:** 프론트엔드의 대기열 폴링 주기(Polling Interval)가 3~5초 간격으로 적절히 쓰로틀링되어 있는지 확인

---

## 13. 트러블슈팅 매뉴얼

| 발생 증상 | 핵심 원인 분석 | 조치 방안 |
| --- | --- | --- |
| **Amplify 빌드 실패** | `package-lock.json` 의존성 버전 정합성 오류 | 로컬 `frontend/`에서 `npm install` 후 lockfile 갱신 커밋 |
| **프론트 API Network Error**| `VITE_API_BASE_URL` 누락 혹은 끝에 `/` 포함 | 환경 변수 값 확인 후 Amplify **Redeploy** |
| **URL 직접 이동 시 404** | SPA 라우팅 규칙 미등록 | Step 09의 `404-200` Rewrite 규칙 주입 확인 |
| **S3 AccessDenied 에러** | Lambda 실행 롤에 버킷 쓰기 권한 누락 | IAM Policy에 `s3:PutObject`, `GetObject` 리소스 확인 |
| **Bedrock AccessDenied** | 해당 리전의 Bedrock 모델 신청 미승인 | AWS 콘솔에서 Nova / Titan 모델 Request Access 승인 |
| **음성 입력(STT) 먹통** | 마이크 접근 보안 정책 차단 | 접속 주소가 `http://`가 아닌 정식 `https://` 도메인인지 확인 |

---

## 14. 형상 관리 통제 기준 (`.gitignore`)

프로덕션 배포 간 생성되는 민감 자산 및 빌드 임시 파일의 커밋 차단 명세입니다.

```text
backend/serverless/samconfig.toml
backend/serverless/.aws-sam/
frontend/dist/
frontend/node_modules/
.env*
src/data/diseases_cleaned.json
src/data/symptom_index.json
src/data/symptom_embeddings_*.json
```
