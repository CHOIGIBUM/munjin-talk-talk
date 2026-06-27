# 테스트 브랜치 안내

이 폴더는 문진톡톡의 추가 테스트 자료를 모아둔 곳입니다. 일반 로컬 테스트는 백엔드/프론트엔드 각 폴더에 있고, 이 폴더에는 실제 AWS 배포 환경을 확인하는 수동 통합 테스트를 둡니다.

```text
tests/
└── aws/
    ├── README.md
    └── test_aws_full.py
```

## 테스트 계층

| 계층 | 위치 | 실행 방식 | 외부 리소스 |
| --- | --- | --- | --- |
| 백엔드 단위/회귀 테스트 | `backend/serverless/tests/` | `pytest` | 기본적으로 없음 |
| 프론트엔드 단위 테스트 | `frontend/src/**/*.test.js` | `npm test` | 없음 |
| AWS 수동 통합 테스트 | `tests/aws/` | 직접 실행 또는 명시 플래그 pytest | Bedrock, DynamoDB, S3, Lambda |
| IR 평가 보조 코드 | `evaluation/ir/` | 평가 스크립트 직접 실행 | Titan/Bedrock 사용 가능 |

## 백엔드 로컬 테스트

백엔드 테스트는 schema, 개인정보 마스킹, 질문 세트, IR query/scoring, 사투리 RAG, orchestration, prompt golden fixture 등을 확인합니다.

```powershell
cd backend\serverless
pytest tests
```

프로젝트 루트에서 직접 실행하면 Python path와 환경변수 상태에 따라 모듈 탐색이 달라질 수 있으므로, 기본 안내는 `backend/serverless` 기준입니다.

주요 테스트 영역:

- `test_privacy_masking.py`, `test_privacy_redaction.py`: 개인정보 제거와 생년월일 미저장 정책
- `test_question_sets.py`: 공개 질문 세트 API 계약
- `test_retrieval_query.py`, `test_retrieval_scoring.py`: IR query 정제와 scoring 로직
- `test_dialect_rag.py`: 방언 pack 검색과 hint 생성
- `test_prompts_golden.py`: LLM prompt의 안전 규칙 유지
- `test_orchestration.py`: 세션 처리와 문진 파이프라인 기본 흐름

## 프론트엔드 로컬 테스트

프론트엔드는 Vitest를 사용합니다.

```powershell
cd frontend
npm test
```

주요 검증 대상은 API client, onepaper adapter, 안전 키워드 설정, 화면 로직의 순수 함수입니다. 실제 AWS API 호출은 프론트엔드 단위 테스트에서 수행하지 않습니다.

## AWS 수동 통합 테스트

AWS 통합 테스트는 일반 로컬 테스트와 분리해서 봅니다.

```powershell
python tests\aws\test_aws_full.py
```

pytest로 실행하려면 명시적으로 플래그를 켭니다.

```powershell
$env:MUNJIN_RUN_AWS_INTEGRATION = "1"
pytest tests\aws\test_aws_full.py -s
```

환경변수와 실행 전 확인 사항은 [AWS 통합 테스트 README](aws/README.md)를 참고합니다.

## IR 평가 보조 코드

`evaluation/ir/`는 일반 단위 테스트가 아니라 IR 후보 검색과 LLM linker 선택 품질을 분리해서 보기 위한 평가 보조 코드입니다. 실제 운영 데이터나 Bedrock raw trace를 공개 저장소에 올리지 않기 위해 sample data와 실행 방법만 문서화합니다.

자세한 내용은 [IR 평가 README](../evaluation/ir/README.md)를 봅니다.

## 관리 원칙

- AWS 리소스 식별자, 접근 코드, 토큰, 버킷명은 커밋하지 않습니다.
- 실제 환자 정보나 민감정보를 fixture에 넣지 않습니다.
- AWS 통합 테스트 실패를 로컬 단위 테스트 실패와 동일하게 해석하지 않습니다.
- 비용이 발생하는 테스트는 CI 기본 경로에 넣지 않습니다.
- Bedrock raw trace와 실행별 output directory는 공개 저장소에 올리지 않습니다.

## 해커톤 제출 관점

심사위원에게 보여주고 싶은 메시지는 다음입니다.

```text
문진톡톡은 빠르게 반복 가능한 로컬 테스트와 실제 배포 리소스를 확인하는 수동 통합 테스트를 분리했다.
덕분에 비용과 보안 위험이 있는 검증은 통제하면서도,
핵심 로직의 회귀는 로컬에서 반복 확인할 수 있다.
```
