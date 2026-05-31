# Project Structure

```text
munjin-talk-talk-mvp/
├── backend/
│   └── serverless/
│       ├── src/
│       │   ├── common.py
│       │   └── handler.py
│       ├── template.yaml
│       ├── s3-cors.json
│       └── README.md
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── doctor/
│   │   │   ├── patient/
│   │   │   ├── staff/
│   │   │   └── tablet/
│   │   ├── config/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── styles/
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docs/
│   ├── DEPLOYMENT.md
│   └── PROJECT_STRUCTURE.md
└── README.md
```

## Runtime Responsibilities

`frontend/`:

- 직원 접수 화면
- 환자 태블릿 문진
- 의사 대기열
- 의사 원페이퍼
- 환자 안내문/출력 화면

`backend/serverless/`:

- 세션 생성과 대기 순번 관리
- S3 presigned upload URL 발급
- Amazon Transcribe polling
- Bedrock 기반 추출, 매칭, 검증, 안내문 생성
- DynamoDB 세션 저장

## Removed From MVP Repository

아래 항목은 MVP 배포 저장소에서 제외했습니다.

- 로컬 IR 실험 패키지
- 100명 persona 테스트 데이터
- diseases/symptom 원천 JSON 데이터
- retrieval dataset builder script
- evaluation output
- embedding cache
- Vite build output
- `node_modules`
