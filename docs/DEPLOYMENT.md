# Deployment Guide

문진톡톡 MVP를 AWS 서버리스 백엔드와 Amplify 프론트엔드로 배포하는 절차입니다.

## 1. Backend

백엔드는 AWS SAM 기반입니다.

```powershell
cd backend/serverless
sam build
sam deploy --guided
```

필요한 AWS 리소스:

- API Gateway HTTP API
- Lambda Python 3.12
- DynamoDB 세션 테이블
- S3 음성/전사 결과 저장 버킷
- Amazon Transcribe
- Amazon Bedrock Nova Pro/Lite

`sam deploy --guided` 입력 예시:

```text
Stack Name: munjin-mvp-backend
AWS Region: ap-northeast-2
Parameter SessionsTableName: <DynamoDB table name>
Parameter ArtifactsBucketName: <S3 bucket name>
Parameter LambdaRoleArn: <Lambda execution role ARN>
Parameter CustomVocabularyName:
Allow SAM CLI IAM role creation: N
```

배포가 끝나면 출력되는 `ApiEndpoint`를 복사합니다.

```text
https://<api-id>.execute-api.ap-northeast-2.amazonaws.com
```

## 2. Frontend Local Build

Node.js `20.19+` 또는 `22.12+`가 필요합니다.

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
```

`frontend/.env.local`:

```text
VITE_API_BASE_URL=https://<api-id>.execute-api.ap-northeast-2.amazonaws.com
```

빌드:

```powershell
npm run build
```

배포 파일은 `frontend/dist` 안에 생성됩니다.

```text
index.html
assets/
```

## 3. Amplify Manual Deploy

1. AWS Amplify 콘솔을 엽니다.
2. `Create new app`을 선택합니다.
3. `Deploy without Git`을 선택합니다.
4. App name은 예: `munjin-talk-talk-mvp`로 입력합니다.
5. Environment name은 예: `prod`로 입력합니다.
6. `Drag and drop`을 선택합니다.
7. `frontend/dist` 내부의 `index.html`과 `assets/`가 zip 루트에 오도록 압축해 업로드합니다.
8. 배포 완료 후 HTTPS URL을 확인합니다.

예시:

```text
https://prod.<app-id>.amplifyapp.com
```

태블릿 마이크 권한 때문에 배포 URL은 HTTPS여야 합니다.

## 4. S3 CORS

Amplify 배포 후 S3 artifact bucket CORS에 Amplify HTTPS URL을 추가합니다.

예시:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "https://prod.<app-id>.amplifyapp.com"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

AWS CLI 적용:

```powershell
aws s3api put-bucket-cors `
  --bucket <S3 bucket name> `
  --cors-configuration file://backend/serverless/s3-cors.json `
  --region ap-northeast-2
```

## 5. Smoke Test

배포된 HTTPS URL에서 아래 순서로 확인합니다.

1. `/staff`: 환자 세션 생성
2. `/patient/{sessionId}`: 태블릿 음성 문진 및 STT 확인
3. `/doctor/queue`: 대기열 확인
4. `/doctor/{sessionId}`: 원페이퍼, 증상 슬롯, 환자 질문, 확인 항목 확인
5. 의료진 답변과 강조사항 입력
6. `/guide/{sessionId}`: 환자 안내문과 출력 화면 확인

## 6. Public Test Before Checklist

- 직원/의사 화면 접근 제한
- S3 CORS에 실제 Amplify URL 반영
- Bedrock 모델 접근 권한 확인
- Lambda CloudWatch 로그 확인
- 실제 환자 개인정보 입력 금지 또는 별도 동의 절차 준비
