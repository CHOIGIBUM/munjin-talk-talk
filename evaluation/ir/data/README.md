# IR Evaluation Data

이 폴더는 문진톡톡 IR/파이프라인 평가에 사용하는 합성 테스트 데이터를 보관합니다.

## Files

| 파일 | 설명 |
| --- | --- |
| `eval_cases.json` | 현재 baseline 평가에 사용하는 100건 합성 데이터셋 |
| `eval_cases.sample.jsonl` | 스키마 확인용 3건 샘플 |
| `raw/munjin_eval_100.json` | 원본 합성 데이터 백업 |

## Current Dataset

- 총 100건
- 초진 60건, 재진 40건
- 표준어 50건, 사투리 50건
- Q1 81건, Q3 19건
- gold 표준 증상 47종
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
  --summary-output evaluation\ir\outputs\baseline_manual\dataset_summary.json
```
