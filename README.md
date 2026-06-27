# 문진톡톡 테스트 커버리지 브랜치

이 브랜치는 실제 서비스 공식 코드가 아니라 기존 테스트에 AWS 통합 점검 자료를 추가한 테스트 브랜치입니다.

## 바로 보기

- [테스트 브랜치 안내](tests/README.md)
- [AWS 통합 테스트 설명](tests/aws/README.md)
- [AWS 통합 테스트 스크립트](tests/aws/test_aws_full.py)

## 해석 기준

`tests/aws/test_aws_full.py`는 실제 Bedrock, DynamoDB, S3, Lambda를 호출하는 수동 통합 테스트입니다. 권한과 비용 영향을 확인한 뒤 실행해야 하며, 일반 단위 테스트와 분리해서 봅니다.

공식 서비스 설명은 [main 브랜치](https://github.com/X-AI-KNU/munjin-talk-talk/tree/main)를 참고하세요.
