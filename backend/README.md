# 문진톡톡 Backend

실제 MVP 백엔드는 `serverless/` 폴더만 사용합니다.

```text
backend/
└── serverless/
    ├── src/
    │   ├── common.py
    │   └── handler.py
    ├── template.yaml
    ├── s3-cors.json
    └── README.md
```

이전 로컬 평가용 IR 데이터, 테스트셋, 실험 스크립트는 배포 MVP에 필요하지 않아 제거했습니다.

백엔드 상세 실행 및 배포 방법은 [serverless/README.md](serverless/README.md)를 참고하세요.
