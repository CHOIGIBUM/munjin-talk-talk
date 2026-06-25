# IR Evaluation Data

이 폴더는 문진톡톡 IR/파이프라인 평가에 사용하는 공개 개발 데이터를 보관합니다.
현재 파일들은 실제 환자 데이터가 아니며, 성능 개선과 회귀 테스트에 사용하는 synthetic/dev 데이터입니다.

## Files

| 파일 | 설명 |
| --- | --- |
| `eval_cases.json` | 사람이 검토해 정리한 100건 공개 개발 데이터셋 |
| `eval_cases.sample.jsonl` | 스키마 확인용 3건 샘플 |
| `raw/munjin_eval_100.json` | 원본 합성 데이터 백업 |
| `synthetic/` | 1000건 공개 합성 회귀 데이터셋 |

## Dataset Roles

| 데이터셋 | 용도 | 블라인드 여부 |
| --- | --- | --- |
| `eval_cases.json` | 프롬프트, few-shot, IR 구조 개선용 curated dev set | 아님 |
| `synthetic/synthetic_1000.json` | 균형 잡힌 공개 회귀 테스트와 분포 확인 | 아님 |
| 새로 생성할 freeze 후 holdout | 최종 성능 보고 | 예 |

현재 1000건 synthetic 데이터는 alias/few-shot 실패 분석에 이미 노출되었으므로 blind benchmark로 사용하지 않습니다.

## Current 100-Case Dataset

- 총 100건
- 초진 60건, 재진 40건
- 표준어 50건, 사투리 50건
- Q1 81건, Q3 19건
- gold 표준 증상 47종
- gold mention 108개
- negative mention 30개
- 모든 `gold_symptoms`, `negative_symptoms`는 현재 `backend/serverless/src/data/symptom_index.json`에 존재해야 합니다.

## Validate

```powershell
python evaluation\ir\validate_eval_data.py `
  --input evaluation\ir\data\eval_cases.json
```

summary 파일까지 저장하려면:

```powershell
python evaluation\ir\validate_eval_data.py `
  --input evaluation\ir\data\eval_cases.json `
  --summary-output evaluation\ir\outputs\eval_clean_manual100_dataset_summary.json
```
