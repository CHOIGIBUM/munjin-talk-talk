# Train 100 v2 Blueprint

이 폴더는 `train_100_v2`를 만들기 위한 row-level blueprint입니다. 실제 환자 발화 텍스트가 아니라, 렌더러가 생성해야 할 증상 조합, 질문 유형, 사투리 source layer, 난이도 조건을 정의합니다.

## 파일

- `distribution_plan.json`: 고정 분포와 생성 규칙입니다.
- `case_blueprint.schema.json`: row schema입니다.
- `case_blueprint.jsonl`: 100개 planned row입니다.
- `quality_gate_report.json`: blueprint 검증 요약입니다.
- `build_blueprint.py`: blueprint 재생성 스크립트입니다.

## 범위

허용된 질문 대상은 초진 Q1 주호소와 재진 Q3 경과/재발 답변입니다. Q2 발생 시점, Q4 의사에게 물어볼 질문, 약물/영양제 질문은 이 데이터셋에서 제외합니다.
