# Train 100 Offline IR/RAG Evaluation

이 평가는 held-out 성능 평가가 아니라, `train_100`으로 재구축한 런타임 artifact가 같은 train set을 후보 검색 단계에서 얼마나 덮는지 보는 sanity check입니다.
Bedrock/LLM은 호출하지 않았고, 실제 런타임의 alias hint와 BM25 symptom index를 사용했습니다.

## Summary

- cases: 100
- total gold labels: 106
- alias gold micro recall: 92.5%
- active alias negative leak case rate: 0.0%
- inactive alias negative marker case rate: 31.0%
- raw BM25 recall@1 / @3 / @5 / @10: 76.4% / 92.5% / 98.1% / 100.0%
- runtime RAG recall@1 / @3 / @5 / @10: 85.9% / 98.1% / 100.0% / 100.0%
- raw BM25 all-hit@5: 98.0%
- runtime RAG all-hit@5: 100.0%
- raw BM25 top1 case accuracy: 81.0%
- runtime RAG top1 case accuracy: 91.0%
- raw BM25 negative-in-top5 case rate: 30.0%
- runtime RAG negative-in-top5 case rate: 0.0%

## Interpretation

- Runtime RAG 후보 검색은 train set 내부에서는 대부분의 gold symptom을 top5 안에 올립니다.
- alias hint는 BM25보다 보수적으로 작동합니다. 모든 gold를 직접 alias로 잡는 구조는 아니며, RAG 후보 보조 역할에 가깝습니다.
- inactive alias marker는 부정/호전 문맥을 prompt hint로 남기되, runtime RAG reference 후보에서는 제외합니다.
- 이 결과는 학습 데이터 자기검사라 일반화 성능으로 보고하면 안 됩니다. 다음 단계는 별도 test set으로 같은 산식을 반복하는 것입니다.

## By Dialect

| group | cases | gold labels | alias recall | BM25 recall@5 | RAG recall@5 | BM25 all-hit@5 | RAG all-hit@5 | BM25 neg@5 | RAG neg@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kangwon | 50 | 50 | 92.0% | 98.0% | 100.0% | 98.0% | 100.0% | 24.0% | 0.0% |
| standard | 50 | 56 | 92.9% | 98.2% | 100.0% | 98.0% | 100.0% | 36.0% | 0.0% |

## By Question

| group | cases | gold labels | alias recall | BM25 recall@5 | RAG recall@5 | BM25 all-hit@5 | RAG all-hit@5 | BM25 neg@5 | RAG neg@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q1 | 50 | 56 | 94.6% | 98.2% | 100.0% | 98.0% | 100.0% | 36.0% | 0.0% |
| Q3 | 50 | 50 | 90.0% | 98.0% | 100.0% | 98.0% | 100.0% | 24.0% | 0.0% |

## Main Failure Buckets

- alias_miss_cases: 8
- bm25_top5_miss_cases: 2
- bm25_top5_negative_leak_cases: 30
- top1_not_gold_cases: 19
- rag_top5_miss_cases: 0
- rag_top5_negative_leak_cases: 0
- rag_top1_not_gold_cases: 9

## Runtime RAG Top5 Gold Miss Cases

- none

## Runtime RAG Negative Leakage Cases

- none

## Alias Miss Samples

- `train_bp_017` Q1 standard | text: 몸살 난 것처럼 온몸이 쑤시고 열도 나 | gold: 근육통, 열 | top5: 근육통, 온몸이 떨림, 가슴 답답, 열, 오한 | alias_miss: 열
- `train_bp_030` Q1 kangwon | text: 열은 좀 나는데 기침은 안 나와 | gold: 열 | top5: 목소리 변화, 열, 삼키기 곤란, 가래, 근력 약화 | alias_miss: 열
- `train_bp_040` Q1 kangwon | text: 기침하고 나면 가래에 피가 살짝 비쳐 | gold: 객혈 | top5: 기침, 가래, 객혈, 검은색 가래, 권태감 | alias_miss: 객혈
- `train_bp_054` Q3 standard | text: 약 먹고 좀 괜찮다가 어제부터 열이 다시 나 | gold: 열 | top5: 열, 빈맥, 빈호흡, 두통, 기침 | alias_miss: 열
- `train_bp_062` Q3 standard | text: 가슴이 아픈 건 괜찮아졌는데 답답한 건 아직 남아 | gold: 가슴 답답 | top5: 가슴 답답, 목의 통증, 복부 통증, 가슴 두근거림, 함몰가슴 | alias_miss: 가슴 답답
- `train_bp_064` Q3 standard | text: 약은 먹었는데도 몸에 힘이 계속 없어 | gold: 기운없음 | top5: 코막힘, 근력 약화, 콧물, 기운없음, 감기 증상 | alias_miss: 기운없음
- `train_bp_077` Q3 kangwon | text: 코가 아직도 맥혀서 답답해 | gold: 코막힘 | top5: 코막힘, 가슴 답답, 복부 통증 | alias_miss: 코막힘
- `train_bp_097` Q3 kangwon | text: 손발이 전보다 부어서 퉁퉁해 | gold: 사지 부종 | top5: 사지 부종, 하지부종, 목소리 변화, 두통, 근육통 | alias_miss: 사지 부종

## Runtime RAG Top1 Not Gold Samples

- `train_bp_010` Q1 standard | text: 가래가 누렇고 진하게 나오는데 피가 섞이진 않았어 | gold: 화농성 객담 | top5: 가래, 화농성 객담, 기침, 검은색 가래, 구토
- `train_bp_011` Q1 standard | text: 가래가 까맣게 섞여 나와서 걱정돼 | gold: 검은색 가래 | top5: 가래, 검은색 가래, 기침, 객혈, 거품이 섞인 가래
- `train_bp_030` Q1 kangwon | text: 열은 좀 나는데 기침은 안 나와 | gold: 열 | top5: 목소리 변화, 열, 삼키기 곤란, 가래, 근력 약화
- `train_bp_037` Q1 kangwon | text: 조금만 움직여도 숨이 벅차서 힘들어 | gold: 호흡곤란 | top5: 운동 시 호흡곤란, 호흡곤란, 가슴 답답, 가래, 복벽이 움푹 들어감
- `train_bp_038` Q1 kangwon | text: 계단만 올라가도 숨이 차는데 가슴이 아픈 건 없어 | gold: 운동 시 호흡곤란 | top5: 호흡곤란, 운동 시 호흡곤란, 가슴 답답, 목의 통증, 복부 통증
- `train_bp_040` Q1 kangwon | text: 기침하고 나면 가래에 피가 살짝 비쳐 | gold: 객혈 | top5: 기침, 가래, 객혈, 검은색 가래, 권태감
- `train_bp_041` Q1 kangwon | text: 몸이 으슬으슬 떨리는데 열은 안 나 | gold: 오한 | top5: 감기 증상, 오한, 온몸이 떨림, 목소리 변화, 근력 약화
- `train_bp_064` Q3 standard | text: 약은 먹었는데도 몸에 힘이 계속 없어 | gold: 기운없음 | top5: 코막힘, 근력 약화, 콧물, 기운없음, 감기 증상
- `train_bp_086` Q3 kangwon | text: 걸을 때마다 숨이 벅차게 차기 시작했어 | gold: 운동 시 호흡곤란 | top5: 호흡곤란, 운동 시 호흡곤란, 가슴 답답, 흉통, 저산소증
