# 문진톡톡 Serverless Backend

이 폴더는 문진톡톡 MVP를 AWS에서 실행하기 위한 서버리스 백엔드입니다.

## API 역할

- `POST /sessions`: 접수 세션 생성
- `POST /upload-url`: 태블릿 음성 업로드용 S3 presigned URL 발급
- `GET /transcribe-result`: Amazon Transcribe 작업 시작 및 결과 조회
- `POST /extract`: Bedrock 기반 발화 추출, 의미 분할, 표준화
- `POST /match`: 추출된 증상 span을 원페이퍼 표시 슬롯으로 변환
- `POST /validate`: 원페이퍼 최종 검토 및 의료진 확인 항목 생성
- `GET /doctor/queue`: 의사 대기열 조회
- `GET /onepager/{session_id}`: 세션별 원페이퍼 조회
- `POST /doctor-response`: 의료진 답변 및 강조사항 저장
- `GET /guide/{session_id}`: 환자 안내문 조회

## AWS 리소스

배포 전에 아래 리소스가 필요합니다.

1. S3 버킷
   - 환자 음성 원본과 Transcribe 결과 JSON 저장
   - 예: `munjin-mvp-artifacts-<account>-<region>`

2. DynamoDB 테이블
   - 세션 상태와 원페이퍼 데이터 저장
   - 파티션 키: `session_id` 문자열

3. Lambda 실행 역할
   - CloudWatch Logs
   - DynamoDB read/write
   - S3 read/write
   - Transcribe start/get
   - Bedrock invoke

4. S3 CORS
   - 브라우저가 presigned URL로 직접 `PUT` 업로드를 수행하므로 필요합니다.
   - 로컬 개발과 Amplify HTTPS 도메인을 `AllowedOrigins`에 추가합니다.

## SAM 배포

AWS CLI 로그인과 SAM CLI 설치가 끝난 상태에서 실행합니다.

```powershell
cd backend/serverless
sam build
sam deploy --guided
```

주요 입력값:

```text
Stack Name: munjin-mvp-backend
AWS Region: ap-northeast-2
Parameter SessionsTableName: <DynamoDB table name>
Parameter ArtifactsBucketName: <S3 bucket name>
Parameter LambdaRoleArn: <Lambda execution role ARN>
Parameter CustomVocabularyName: <없으면 빈 값>
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: N
Save arguments to configuration file: Y
```

배포가 끝나면 출력되는 `ApiEndpoint` 값을 프론트엔드 환경변수에 넣습니다.

```powershell
cd ../../frontend
Copy-Item .env.example .env.local
Set-Content -Encoding UTF8 .env.local "VITE_API_BASE_URL=https://<api-id>.execute-api.ap-northeast-2.amazonaws.com"
```

## S3 CORS 예시

`s3-cors.json`에는 로컬 개발용 origin만 들어 있습니다. Amplify 배포 후에는 배포된 HTTPS URL을 추가해야 합니다.

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "https://<amplify-domain>.amplifyapp.com"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

AWS CLI로 적용:

```powershell
aws s3api put-bucket-cors `
  --bucket <S3 bucket name> `
  --cors-configuration file://s3-cors.json `
  --region ap-northeast-2
```

## Bedrock 모델 라우팅

- Q1 증상/재진 경과: `apac.amazon.nova-pro-v1:0`
- Q2/Q3/Q4 단순 구조화: `apac.amazon.nova-lite-v1:0`
- 원페이퍼 최종 검토: `apac.amazon.nova-pro-v1:0`
- 환자 안내문 쉬운 표현 변환: `apac.amazon.nova-lite-v1:0`

운영 환경에서는 Lambda 환경변수 기준으로 `USE_BEDROCK_LLM=true`, `ALLOW_RULE_FALLBACK=false`를 사용합니다.

## MVP 한계

- 로그인/권한 분리는 아직 없습니다.
- 외부 공개 전에는 Cognito, Amplify 접근 제한, 병원 내부망 또는 VPN이 필요합니다.
- Bedrock 호출 비용과 지연 시간이 실제 문진 속도에 반영됩니다.
