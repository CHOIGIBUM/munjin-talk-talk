# 문진톡톡 사투리 RAG 평가 브랜치

이 브랜치는 문진톡톡 공식 서비스 코드가 아니라, 사투리 RAG가 문진 답변의 의미를 보존하면서 표준어 보조 문장 생성을 돕는지 확인한 평가 자료 브랜치입니다.

공식 서비스 설명과 실행 코드는 [main 브랜치](https://github.com/X-AI-KNU/munjin-talk-talk/tree/main)를 기준으로 봅니다. 이 브랜치는 해커톤 제출 시 "사투리 RAG 실험과 성능 점검 근거"를 따로 보여주기 위해 분리했습니다.

## 평가 질문

고령 환자는 문진 과정에서 사투리, 구어체, 지역 표현을 섞어 말할 수 있습니다. 문진톡톡의 사투리 RAG는 이런 표현을 바로 진단이나 증상명으로 확정하지 않고, 강원 방언팩에서 찾은 힌트를 Bedrock 표준어 변환 프롬프트에 참고 정보로 넣습니다.

이 브랜치에서 확인하는 질문은 하나입니다.

```text
사투리/구어체 문진 답변을 표준어 보조 문장으로 바꿨을 때,
환자가 말한 증상, 부정 표현, 시점, 정도, 복약 사실, 질문 의도가 유지되는가?
```

## 바로 보기

| 문서/파일 | 내용 |
| --- | --- |
| [평가 상세 설명](evaluation/dialect_rag/README.md) | 평가 목적, 데이터 구조, 실행 방법, 지표 해석 |
| [평가 요약 지표](evaluation/dialect_rag/reports/summary.json) | 200개 케이스 기준 집계 결과 |
| [실패 케이스](evaluation/dialect_rag/reports/failed_cases.csv) | 의미 불일치, 정보 추가/누락 등 실패 사례 |
| [평가 데이터](evaluation/dialect_rag/data/dialect_norm_eval_200.jsonl) | 사투리/구어체 입력과 기준 표준어 문장 |
| [평가 스크립트](evaluation/dialect_rag/run_dialect_semantic_eval.py) | RAG 힌트 검색, Bedrock 변환, Bedrock judge 평가 |
| [방언팩 위치 안내](backend/serverless/src/data/README.md) | `dialect_packs/dialect_kangwon.json` 역할 설명 |

## 평가 흐름

```text
평가 입력 문장
  -> local_dialect_rag가 강원 방언팩에서 힌트 검색
  -> Bedrock Nova Lite가 표준어 보조 문장 생성
  -> Bedrock Nova Lite judge가 원문/정답/생성문 비교
  -> summary.json과 failed_cases.csv로 결과 정리
```

평가 스크립트는 `backend/serverless/src/dialect_rag.py`의 `retrieve_dialect_context()`를 사용합니다. 이 함수는 `dialect_packs/dialect_kangwon.json`에서 방언 표현을 찾아 `prompt_note` 형태의 힌트를 만들고, normalizer 프롬프트는 이 힌트를 "어휘 참고"로만 사용합니다. 원문에 없는 증상, 약, 시점, 정도를 추가하지 말라는 제한도 함께 들어갑니다.

## 현재 결과 요약

`evaluation/dialect_rag/reports/summary.json` 기준입니다.

| 항목 | 값 | 의미 |
| --- | ---: | --- |
| 평가 케이스 수 | 200 | synthetic/starter set 기준 |
| 변환 모델 | `apac.amazon.nova-lite-v1:0` | 표준어 보조 문장 생성 |
| Judge 모델 | `apac.amazon.nova-lite-v1:0` | 의미 보존 여부 판정 |
| 의미 성공률 | 0.900 | 아래 4개 조건을 모두 통과한 비율 |
| 동일 의미 판정률 | 0.925 | 원문 의미가 유지됐다고 본 비율 |
| 표준어 판정률 | 0.990 | 생성문이 자연스러운 표준어라고 본 비율 |
| 정보 추가 없음 | 0.965 | 원문에 없는 증상/약/시점/정도 등이 추가되지 않은 비율 |
| 정보 누락 없음 | 0.930 | 원문에 있던 핵심 정보가 빠지지 않은 비율 |
| 평균 RAG 힌트 수 | 0.275 | 케이스당 검색된 방언 힌트 평균 |

`semantic_success_rate`는 다음 네 조건을 동시에 만족해야 성공으로 계산됩니다.

- `same_meaning == true`
- `standard_korean == true`
- `added_fact == false`
- `omitted_fact == false`

실패 유형은 `added_fact` 7건, `meaning_mismatch` 1건, `not_standard_korean` 2건, `omitted_fact` 10건입니다. 실패 사례는 [failed_cases.csv](evaluation/dialect_rag/reports/failed_cases.csv)에서 원문, 기준 표준어, 모델 변환문, judge 사유까지 함께 확인할 수 있습니다.

## 제출 시 해석 기준

이 결과는 "문진톡톡이 사투리 표현을 표준어 보조 문장으로 옮길 때 의미 보존을 얼마나 유지했는가"를 보여주는 내부 평가입니다.

다음처럼 표현하는 것은 적절합니다.

- 사투리/구어체 문진 답변 200개 starter set에 대해 의미 보존 평가를 수행했다.
- 정보 추가와 정보 누락을 별도 지표로 분리해 의료 문진에서 위험한 변환을 확인했다.
- 실패 케이스를 따로 남겨 어떤 표현에서 변환이 흔들리는지 검토할 수 있게 했다.

다음처럼 표현하면 안 됩니다.

- 병원 실데이터 전체에서 검증된 임상 성능이라고 주장
- 진단, 처방, 질병 예측 성능으로 해석
- 모든 지역 방언과 모든 진료과에 일반화된 성능으로 주장

이 브랜치는 서비스 기능을 과장하기 위한 문서가 아니라, 사투리 RAG가 어디까지 동작했고 어디에서 실패했는지 투명하게 보여주는 평가 기록입니다.
