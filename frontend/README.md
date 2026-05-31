# 문진톡톡 Frontend

React + Vite 기반 MVP 프론트엔드입니다.

## 실행

Node.js `20.19+` 또는 `22.12+`가 필요합니다.

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev -- --host 127.0.0.1 --port 5173
```

`VITE_API_BASE_URL`이 비어 있으면 mock 데이터로 동작합니다. 실제 AWS 백엔드를 붙이려면 `.env.local`에 API Gateway 주소를 넣습니다.

```text
VITE_API_BASE_URL=https://<api-id>.execute-api.ap-northeast-2.amazonaws.com
```

## 주요 경로

```text
/staff                 직원 접수 화면
/patient/:sessionId    환자 태블릿 문진
/doctor/queue          의사 대기열
/doctor/:sessionId     의사 원페이퍼
/guide/:sessionId      환자 안내문
```

## 구성

```text
src/
├── App.jsx
├── main.jsx
├── assets/
├── components/
│   ├── staff/
│   ├── patient/
│   ├── doctor/
│   └── tablet/
├── config/
├── hooks/
├── services/
└── styles/
```

## 동작 흐름

1. `ReceptionView`에서 환자 세션을 생성합니다.
2. `PatientKioskView`와 `PatientFlow`가 Q1-Q4 음성 문진을 진행합니다.
3. `api.js`가 S3 presigned upload, Transcribe polling, Bedrock extraction/match/validate API를 호출합니다.
4. `DoctorView`가 원페이퍼와 답변 입력 패널을 보여줍니다.
5. `PatientGuideScreen`이 환자 안내문을 보여주고 출력/공유 UI를 제공합니다.

## 빌드

```powershell
npm run build
```

빌드 결과는 `dist/`에 생성됩니다. Git에는 커밋하지 않습니다.

## 주의

- 실제 태블릿 마이크 입력은 HTTPS 또는 localhost에서만 안정적으로 동작합니다.
- 운영 공개 전에는 직원/의사 화면에 인증 또는 접근 제한이 필요합니다.
