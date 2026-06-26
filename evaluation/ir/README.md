# 문진톡톡 IR 평가

이 폴더는 문진톡톡의 표준 증상 검색과 최종 매칭 성능을 평가하기 위한 코드만 보관합니다. 생성 데이터, 평가 출력물, alias, few-shot 보강물은 출처와 역할이 섞이지 않도록 별도 폴더에서 관리합니다.

## 평가 흐름

```text
환자 발화
  -> 운영 파이프라인 기반 표준화/의미 span 추출
  -> active symptom span만 IR 입력
  -> query = normalized_text + symptom_hint
  -> BM25 + vector + label signal
  -> RRF hybrid ranking
  -> top-k 표준 증상 후보
  -> linker
  -> 후보 밖 선택 금지 validator
  -> 최종 표준 증상 평가
```

평가는 두 층으로 나눠 봅니다.

| 층 | 확인하는 것 |
| --- | --- |
| 후보 검색 | 정답 표준 증상이 top-k 후보 안에 들어왔는가 |
| 최종 선택 | 후보 중에서 linker가 실제 정답을 선택했는가 |

## 파일 구성

| 경로 | 역할 |
| --- | --- |
| `run_pipeline_eval.py` | 평가 문장을 운영 파이프라인에 넣어 `normalized_text`, `status`, `symptom_hint` 생성 |
| `run_ir_eval.py` | 생성된 span으로 IR 후보 검색과 linker 평가 수행 |
| `run_eval_suite.py` | 파이프라인 생성과 IR 평가를 이어서 실행 |
| `run_baseline.ps1` | 데이터 검증, 빠른 IR baseline, 선택적 전체 baseline 실행 |
| `validate_eval_data.py` | gold/negative 증상명과 방문유형-문항 조합 검증 |
| `data/` | 공개 개발 데이터와 새 생성 데이터 위치 |
| `dataset_generation/` | train 100, test 1000 생성 프레임워크 문서 |
| `derived/` | train 100에서 파생한 alias/few-shot 제안 위치 |
| `outputs/` | 로컬 평가 실행 결과. 기본적으로 Git에 올리지 않음 |
| `cache/` | embedding cache. Git 관리 대상 아님 |

## 평가 데이터 형식

평가 데이터에는 환자 발화와 정답 표준 증상명만 넣습니다. `normalized_text`, `symptom_hint`, query term은 사람이 미리 쓰지 않고 실제 파이프라인으로 생성합니다.

```json
{
  "case_id": "train_001",
  "visit_type": "초진",
  "dialect_type": "standard",
  "question_id": "Q1",
  "text": "어제부터 목이 칼칼하고 코가 막혀요.",
  "gold_symptoms": ["목의 통증", "코막힘"],
  "negative_symptoms": []
}
```

`gold_symptoms`와 `negative_symptoms`는 운영 표준 증상 목록에 존재하는 이름이어야 합니다.

## 데이터 역할

| 데이터셋 | 용도 | alias/few-shot 반영 가능 여부 | 성능 보고 |
| --- | --- | --- | --- |
| `data/eval_cases.json` | 기존 100건 개발 데이터 보존 및 회귀 확인 | 가능 | 최종 성능으로 보고하지 않음 |
| `data/generated/train_100/cases.json` | 새 v2 alias/few-shot 설계용 training set | 가능 | 최종 성능으로 보고하지 않음 |
| `data/generated/test_1000/cases.locked.json` | 새 v2 평가용 locked test set | 불가 | 개별 실패를 열기 전 1회 성능 보고 가능 |

중요한 규칙은 단순합니다. `test_1000`의 개별 실패를 보고 alias, few-shot, prompt, matcher를 고치면 그 데이터는 더 이상 blind test가 아닙니다. 이 경우 새 `test_1000`을 다시 생성해야 합니다.

## 실행 예시

파이프라인 span 생성:

```powershell
python evaluation\ir\run_pipeline_eval.py `
  --input evaluation\ir\data\generated\test_1000\cases.locked.json `
  --output-dir evaluation\ir\outputs\test_1000_pipeline
```

IR 후보만 빠르게 확인:

```powershell
python evaluation\ir\run_ir_eval.py `
  --input evaluation\ir\outputs\test_1000_pipeline\pipeline_ir_eval_cases.jsonl `
  --output-dir evaluation\ir\outputs\test_1000_ir `
  --skip-llm-judge
```

전체 suite 실행:

```powershell
python evaluation\ir\run_eval_suite.py `
  --input evaluation\ir\data\generated\test_1000\cases.locked.json `
  --output-dir evaluation\ir\outputs\test_1000_full `
  --top-k 20
```

## 보고 원칙

- IR recall과 최종 F1은 반드시 분리해서 보고합니다.
- `train_100`으로 만든 alias/few-shot의 출처는 `derived/`에 남깁니다.
- `test_1000` 실패 사례를 열람한 뒤에는 같은 파일을 최종 test로 재사용하지 않습니다.
- 평가 출력물은 재현이 필요할 때만 로컬에 두고, Git에는 기본적으로 올리지 않습니다.
