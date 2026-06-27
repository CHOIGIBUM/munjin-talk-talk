# 문진톡톡 서비스 검증 브랜치

본 브랜치(`test/service-validation`)는 문진톡톡 공식 서비스 코드와 분리되어, 로컬 회귀 테스트와 실제 AWS 배포 환경 수동 통합 테스트를 정리한 서비스 검증 브랜치입니다.

공식 서비스 아키텍처, 배포 기준, 사용자 화면 흐름은 [main 브랜치](https://github.com/X-AI-KNU/munjin-talk-talk/tree/main)를 기준으로 합니다. 이 브랜치는 해커톤 심사 및 기술 검토 과정에서 "서비스가 어떤 테스트 계층으로 검증되었고, 실제 AWS 리소스와 연결된 흐름을 어떻게 확인할 수 있는가"를 설명하기 위해 남겼습니다.

## 1. 서비스 검증 목적

문진톡톡은 프론트엔드, 서버리스 백엔드, Bedrock, DynamoDB, S3, Lambda, API Gateway가 함께 동작하는 서비스입니다. 단순히 화면이 열리는지만 확인해서는 실제 문진 파이프라인의 안전성을 설명하기 어렵습니다.

이 브랜치는 테스트 비율 수치를 주장하기 위한 브랜치가 아닙니다. 대신 비용이 들지 않는 로컬 회귀 테스트와 실제 AWS 리소스를 호출하는 수동 통합 검증을 분리해, 검증 범위와 실행 조건을 투명하게 보여줍니다.

| 계층 | 위치 | 기본 실행 성격 | 외부 리소스 |
| --- | --- | --- | --- |
| 백엔드 단위/회귀 테스트 | `backend/serverless/tests/` | 로컬 pytest | 기본적으로 없음 |
| 프론트엔드 단위 테스트 | `frontend/src/**/*.test.js` | 로컬 Vitest | 없음 |
| AWS 수동 통합 테스트 | `tests/aws/test_aws_full.py` | 명시적으로만 실행 | Bedrock, DynamoDB, S3, Lambda |
| IR 평가 보조 코드 | `evaluation/ir/` | 평가 스크립트 직접 실행 | Titan/Bedrock 사용 가능 |

## 2. 바로 보기

| 문서/파일 | 내용 |
| --- | --- |
| [서비스 검증 테스트 안내](tests/README.md) | 로컬 테스트, AWS 통합 테스트, IR 평가 보조 코드의 구분 |
| [AWS 통합 테스트 설명](tests/aws/README.md) | 환경변수, 실행 전 체크리스트, 실패 해석 |
| [AWS 통합 테스트 스크립트](tests/aws/test_aws_full.py) | 실제 Bedrock, DynamoDB, S3, Lambda 호출 |
| [IR 평가 안내](evaluation/ir/README.md) | 표준 증상 후보 검색과 linker 평가 보조 코드 |
| [백엔드 테스트 fixture 안내](backend/serverless/tests/fixtures/README.md) | golden prompt, fixture 관리 기준 |

## 3. AWS 통합 테스트 범위

`tests/aws/test_aws_full.py`는 다음 항목을 수동으로 확인합니다.

- Bedrock Nova Lite / Nova Pro 호출
- Titan Text Embedding v2 호출
- DynamoDB 세션 조회와 PII 미저장 구조 확인
- S3 artifact bucket 접근과 onepaper/answers artifact 구조 확인
- Lambda 라우팅, 인증 실패, 입력 검증 확인
- 기존 세션을 이용한 process-answer 파이프라인 E2E
- 증상 추출 프롬프트와 사투리/표준어 변환 schema 확인
- 잘못된 접근 코드와 세션 토큰 접근 제어 확인

이 테스트는 일반 CI에서 자동으로 돌리는 테스트가 아닙니다. 실제 AWS 리소스를 호출하므로 배포 상태, 권한, 비용 영향을 확인한 뒤 명시적으로 실행합니다.

## 4. 실행 기준

로컬 테스트는 반복 실행해도 비용 영향이 없도록 설계합니다.

```powershell
cd backend\serverless
pytest tests
```

```powershell
cd frontend
npm test
```

AWS 통합 테스트는 직접 실행하거나, pytest에서 명시 플래그를 켠 경우에만 실행합니다.

```powershell
python tests\aws\test_aws_full.py
```

```powershell
$env:MUNJIN_RUN_AWS_INTEGRATION = "1"
pytest tests\aws\test_aws_full.py -s
```

`MUNJIN_RUN_AWS_INTEGRATION`을 설정하지 않으면 pytest import 단계에서 skip되도록 구성되어 있습니다. 이는 전체 테스트 실행 중 실수로 Bedrock과 AWS 리소스를 호출하지 않기 위한 안전장치입니다.

## 5. 제출 시 해석 기준

해커톤 제출에서는 다음처럼 설명하는 것이 적절합니다.

```text
문진톡톡은 로컬 단위/회귀 테스트와 AWS 수동 통합 테스트를 분리해 관리했다.
일반 테스트는 반복 실행 가능하도록 비용 없는 로컬 경로에 두었고,
Bedrock, DynamoDB, S3, Lambda를 실제로 호출하는 검증은 명시 플래그와 별도 문서로 분리했다.
```

피해야 할 표현:

- AWS 통합 테스트가 일반 CI에서 항상 자동 실행된다고 주장
- 통합 테스트 통과를 의학적 성능 검증으로 해석
- 실제 API URL, Lambda 이름, 버킷명, credential을 README에 고정 공개
- 실제 환자 정보나 운영 trace를 fixture에 포함

## 6. 브랜치의 의미

이 브랜치는 "운영 배포가 항상 안전하다"는 보장이 아닙니다. 대신 어떤 계층을 어떤 방식으로 검증했고, 비용/권한/민감정보가 걸린 테스트를 어떻게 분리했는지 보여주는 테스트 근거입니다.

따라서 main 브랜치의 공식 서비스 설명과 함께 보면 다음 역할을 합니다.

| main 브랜치 | test/service-validation 브랜치 |
| --- | --- |
| 서비스 구조, 배포, 사용자 흐름 설명 | 검증 계층, 실행 명령, AWS 통합 확인 기준 설명 |
| 최종 제출용 공식 문서 | 테스트 근거와 운영 검증 보조 문서 |
