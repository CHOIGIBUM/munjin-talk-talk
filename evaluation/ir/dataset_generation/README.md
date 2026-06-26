# Dataset Generation v2

이 폴더는 문진톡톡 IR 평가 데이터를 새로 만들기 위한 설명 가능한 생성 프레임워크입니다. 과거처럼 코드가 문장을 조합해서 데이터셋을 만드는 방식은 사용하지 않습니다. 코드는 분포와 금지 규칙을 담은 blueprint를 만들고, 실제 환자 발화 문장은 LLM이 blueprint를 해석해 자연스럽게 생성합니다.

## 목표

1. 구조는 고정합니다.
2. train 100과 test 1000은 따로 생성합니다.
3. train 100으로만 alias/few-shot을 만듭니다.
4. test 1000은 개별 실패를 보기 전까지 locked test로 둡니다.
5. 모든 alias/few-shot은 어떤 train case에서 필요해졌는지 설명 가능해야 합니다.

## 산출물

| 산출물 | 위치 | 용도 |
| --- | --- | --- |
| train blueprint | `../data/generated/train_100/blueprint.json` | 100건 생성 설계 |
| train cases | `../data/generated/train_100/cases.json` | alias/few-shot 개발 |
| train manifest | `../data/generated/train_100/manifest.json` | 생성 조건과 검증 기록 |
| test blueprint | `../data/generated/test_1000/blueprint.json` | 1000건 생성 설계 |
| locked test cases | `../data/generated/test_1000/cases.locked.json` | 성능 평가 |
| test manifest | `../data/generated/test_1000/manifest.json` | 생성 조건과 lock 기록 |
| alias proposals | `../derived/alias_proposals.train100.json` | train 100 기반 alias 제안 |
| few-shot proposals | `../derived/fewshot_proposals.train100.json` | train 100 기반 few-shot 제안 |

## 생성 단계

```text
표준 증상 목록 + 도메인팩 + 강원도 dialect pack
  -> generation blueprint 작성
  -> LLM render: 자연스러운 반말/구어체 환자 발화 생성
  -> validator: 스키마, 분포, 직접 증상명 노출, 문항 적합성 검증
  -> train_100 저장
  -> train_100으로 alias/few-shot 제안 생성
  -> 규칙 freeze
  -> 별도 seed로 test_1000 생성
  -> test_1000 locked
```

## 기본 분포

현재 증상 IR 평가의 기본 범위는 아래처럼 둡니다.

| 차원 | train 100 | test 1000 |
| --- | ---: | ---: |
| 초진 Q1 | 50 | 500 |
| 재진 Q3 | 50 | 500 |
| 표준어/일반 구어체 | 50 | 500 |
| 강원도 사투리/지역 구어체 | 50 | 500 |

Q2와 Q4는 이번 IR test의 기본 범위에서 제외합니다. Q2/Q4는 전체 문진 품질 평가나 별도 intent/status 평가로 분리합니다.

## 증상 표현 정책

환자 발화는 모든 표준 증상명을 그대로 말하게 만들지 않습니다. 표현 정책은 세 단계로 나눕니다.

| 유형 | 원칙 | 예 |
| --- | --- | --- |
| 직접 표현 허용 | 일반 환자도 흔히 말하는 쉬운 증상명은 그대로 가능 | 기침, 콧물, 가래, 두통, 설사, 구토 |
| 생활어 우선 | 의학적 표준명보다 일상 표현을 우선 | 목의 통증 -> 목이 아파, 복부 팽만감 -> 배가 빵빵해 |
| 직접 노출 금지 | 복잡하거나 의학적인 표준명은 그대로 쓰지 않음 | 천명음, 객혈, 호흡곤란, 흉통, 부종 |

이 정책은 치팅 방지용입니다. 쉬운 증상은 현실적으로 환자가 직접 말할 수 있지만, 어려운 표준 증상명까지 그대로 넣으면 IR 평가가 정답지 암기에 가까워집니다.

## 사투리 정책

- dialect case는 강원도 dialect pack을 참고합니다.
- 사투리 단어를 억지로 많이 넣지 않습니다.
- 핵심 증상 의미가 흐려지면 안 됩니다.
- 문체는 `습니다`체가 아니라 반말/구어체를 기본으로 합니다.
- 사투리는 표준어 문장을 단순 치환하는 것이 아니라, 지역 구어체 느낌으로 다시 말하게 합니다.

## LLM renderer 규칙

LLM은 blueprint의 `gold_symptoms`, `visit_type`, `question_id`, `dialect_type`, `difficulty`, `expression_policy`를 보고 발화만 생성합니다.

LLM이 하면 안 되는 것:

- gold symptom을 바꾸기
- Q1/Q3 범위를 바꾸기
- test set에 train case 문장을 재사용하기
- 직접 노출 금지 표준 증상명을 그대로 쓰기
- 설명문이나 EMR 문체로 쓰기

## 검증 규칙

생성 후 validator는 최소한 아래를 확인합니다.

- schema valid
- case_id 중복 없음
- train/test 텍스트 중복 없음
- visit_type/question_id 조합 valid
- 표준어 50%, 사투리 50%
- 초진 Q1 50%, 재진 Q3 50%
- gold/negative 표준 증상명이 운영 증상 목록에 존재
- 직접 노출 금지 증상명이 환자 발화에 그대로 포함되지 않음
- `습니다`, `합니다`, `문의드립니다` 같은 문체 과다 사용 없음

## 치팅 방지 원칙

`train_100`은 보강용입니다. 여기서 alias/few-shot을 만드는 것은 허용됩니다.

`test_1000`은 평가용입니다. 여기서 나온 실패를 보고 alias/few-shot을 추가하면, 그 순간 test가 training data가 됩니다. 이 경우 새 `test_1000`을 생성하고 기존 test는 regression 자료로만 남깁니다.
