# IR Evaluation Data

이 폴더는 문진톡톡 IR/파이프라인 평가에 사용하는 공개 개발 데이터와 새로 생성할 평가 데이터를 보관합니다. 실제 환자 데이터는 넣지 않습니다.

## 현재 보존 파일

| 파일 | 설명 |
| --- | --- |
| `eval_cases.json` | 기존 100건 공개 개발 데이터셋. 이미 실패 분석에 노출된 dev set입니다. |
| `eval_cases.sample.jsonl` | 스키마 확인용 샘플 |
| `raw/munjin_eval_100.json` | 기존 원본 합성 데이터 백업 |

## 새 v2 데이터 위치

새 데이터는 아직 생성하지 않았습니다. 생성 후에는 아래 위치에 둡니다.

| 경로 | 용도 |
| --- | --- |
| `generated/train_100/cases.json` | alias/few-shot/domain 보강에 사용할 100건 training set |
| `generated/train_100/manifest.json` | 생성 조건, 모델, seed, 검증 요약 |
| `generated/test_1000/cases.locked.json` | 최종 평가 전까지 개별 실패를 보지 않는 1000건 locked test set |
| `generated/test_1000/manifest.json` | 생성 조건, 모델, seed, 검증 요약, lock 여부 |

## 데이터 분리 규칙

- `train_100`은 열람과 실패 분석이 가능합니다.
- `train_100`에서 만든 alias/few-shot은 반드시 `evaluation/ir/derived/`에 근거를 남깁니다.
- `test_1000`은 성능 측정용입니다.
- `test_1000`의 개별 실패를 분석해서 코드를 바꾸면 새 test set을 다시 생성합니다.
- 표준어 50%, 강원도 사투리/구어체 50% 비율을 기본으로 합니다.
- 현재 증상 IR 평가는 초진 Q1, 재진 Q3를 우선 대상으로 합니다.

## 검증

```powershell
python evaluation\ir\validate_eval_data.py `
  --input evaluation\ir\data\generated\train_100\cases.json
```

```powershell
python evaluation\ir\validate_eval_data.py `
  --input evaluation\ir\data\generated\test_1000\cases.locked.json `
  --summary-output evaluation\ir\outputs\test_1000_validation_summary.json
```
