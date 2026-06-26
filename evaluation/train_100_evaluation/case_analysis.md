# Train 100 Offline IR/RAG Evaluation

이 평가는 held-out 성능 평가가 아니라, `train_100`으로 재구축한 런타임 artifact가 같은 train set을 후보 검색 단계에서 얼마나 덮는지 보는 sanity check입니다.
Bedrock/LLM은 호출하지 않았고, 실제 런타임의 alias hint와 BM25 symptom index를 사용했습니다.

## Summary

- cases: 100
- total gold labels: 106
- alias gold micro recall: 91.5%
- BM25 recall@1 / @3 / @5 / @10: 75.5% / 88.7% / 93.4% / 96.2%
- case all-hit@5: 93.0%
- top1 case accuracy: 80.0%
- negative-in-top5 case rate: 21.0%

## Interpretation

- IR 후보 검색이 train set 내부에서도 gold symptom을 충분히 올리지 못합니다.
- alias hint는 BM25보다 보수적으로 작동합니다. 모든 gold를 직접 alias로 잡는 구조는 아니며, RAG 후보 보조 역할에 가깝습니다.
- 부정된 증상도 lexical 후보에는 자주 올라옵니다. 최종 판정은 LLM span type/status와 IR gate가 막아야 합니다.
- 이 결과는 학습 데이터 자기검사라 일반화 성능으로 보고하면 안 됩니다. 다음 단계는 별도 test set으로 같은 산식을 반복하는 것입니다.

## By Dialect

| group | cases | gold labels | alias recall | BM25 recall@5 | all-hit@5 | negative-in-top5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| kangwon | 50 | 50 | 90.0% | 98.0% | 98.0% | 16.0% |
| standard | 50 | 56 | 92.9% | 89.3% | 88.0% | 26.0% |

## By Question

| group | cases | gold labels | alias recall | BM25 recall@5 | all-hit@5 | negative-in-top5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q1 | 50 | 56 | 94.6% | 91.1% | 90.0% | 28.0% |
| Q3 | 50 | 50 | 88.0% | 96.0% | 96.0% | 14.0% |

## Main Failure Buckets

- alias_miss_cases: 9
- bm25_top5_miss_cases: 7
- bm25_top5_negative_leak_cases: 21
- top1_not_gold_cases: 20

## Top5 Gold Miss Cases

- `train_bp_003` Q1 standard | text: 열은 나는데 춥거나 몸이 떨리는 건 없어 | gold: 열 | top5: 온몸이 떨림, 오한, 감기 증상, 삼키기 곤란, 가슴 답답 | missed@5: 열
- `train_bp_004` Q1 standard | text: 감기 걸린 것처럼 몸이 으슬하고 기침이 나와 | gold: 감기 증상, 기침 | top5: 감기 증상, 가슴 답답, 삼키기 곤란, 목소리 변화, 검은색 가래 | missed@5: 기침
- `train_bp_007` Q1 standard | text: 기침이 계속 나와서 왔어 | gold: 기침 | top5: 콧물, 코막힘, 결막염, 삼키기 곤란, 가슴 답답 | missed@5: 기침
- `train_bp_020` Q1 standard | text: 물 마실 때 자꾸 사레가 들리는데 음식이 안 넘어가진 않아 | gold: 사래걸림 | top5: 삼키기 곤란, 천명음, 설사, 가슴 답답, 발한 | missed@5: 사래걸림
- `train_bp_030` Q1 kangwon | text: 열은 좀 나는데 기침은 안 나와 | gold: 열 | top5: 목소리 변화, 삼키기 곤란, 근력 약화, 가래, 천명음 | missed@5: 열
- `train_bp_056` Q3 standard | text: 열은 이제 없는데 기침이 계속 남아 있어 | gold: 기침 | top5: 콧물, 코막힘, 결막염, 삼키기 곤란, 가슴 답답 | missed@5: 기침
- `train_bp_070` Q3 standard | text: 물을 마실 때마다 자꾸 사레가 들어 | gold: 사래걸림 | top5: 설사, 복벽이 움푹 들어감, 근력 약화, 천명음, 발한 | missed@5: 사래걸림

## Negative Leakage Cases

- `train_bp_003` Q1 standard | text: 열은 나는데 춥거나 몸이 떨리는 건 없어 | gold: 열 | top5: 온몸이 떨림, 오한, 감기 증상, 삼키기 곤란, 가슴 답답 | negative: 오한 | negative@5: 오한
- `train_bp_006` Q1 standard | text: 목이 따갑게 아픈데 음식이 안 넘어가는 정도는 아니야 | gold: 목의 통증 | top5: 목의 통증, 삼키기 곤란, 코막힘, 흉통, 콧물 | negative: 삼키기 곤란 | negative@5: 삼키기 곤란
- `train_bp_010` Q1 standard | text: 가래가 누렇고 진하게 나오는데 피가 섞이진 않았어 | gold: 화농성 객담 | top5: 화농성 객담, 가래, 객혈, 기침, 검은색 가래 | negative: 객혈 | negative@5: 객혈
- `train_bp_012` Q1 standard | text: 숨이 차서 말하기가 좀 힘든데 가슴이 아프진 않아 | gold: 호흡곤란 | top5: 호흡곤란, 가슴 답답, 목의 통증, 흉통, 가슴 두근거림 | negative: 흉통 | negative@5: 흉통
- `train_bp_013` Q1 standard | text: 숨쉴 때 가슴 한쪽이 콕콕 아픈데 숨이 차진 않아 | gold: 흉통 | top5: 흉통, 가슴 답답, 호흡곤란, 가슴 두근거림, 함몰가슴 | negative: 호흡곤란 | negative@5: 호흡곤란
- `train_bp_019` Q1 standard | text: 목소리가 쉬어서 잘 안 나오는데 목이 아픈 건 아니야 | gold: 목소리 변화 | top5: 목소리 변화, 목의 통증, 가래, 객혈, 근력 약화 | negative: 목의 통증 | negative@5: 목의 통증
- `train_bp_020` Q1 standard | text: 물 마실 때 자꾸 사레가 들리는데 음식이 안 넘어가진 않아 | gold: 사래걸림 | top5: 삼키기 곤란, 천명음, 설사, 가슴 답답, 발한 | negative: 삼키기 곤란 | negative@5: 삼키기 곤란
- `train_bp_022` Q1 standard | text: 가슴이 자꾸 두근거리는데 아픈 건 없어 | gold: 가슴 두근거림 | top5: 가슴 두근거림, 가슴 답답, 설사, 흉통, 발한 | negative: 흉통 | negative@5: 흉통
- `train_bp_025` Q1 standard | text: 속이 울렁거리고 토했는데 설사는 안 해 | gold: 구토 | top5: 구토, 설사, 가슴 답답, 근력 약화, 삼키기 곤란 | negative: 설사 | negative@5: 설사
- `train_bp_035` Q1 kangwon | text: 가래가 거품 낀 것처럼 나오는데 피는 안 보여 | gold: 거품이 섞인 가래 | top5: 거품이 섞인 가래, 객혈, 가래, 가슴 답답, 기침 | negative: 객혈 | negative@5: 객혈
- `train_bp_038` Q1 kangwon | text: 계단만 올라가도 숨이 차는데 가슴이 아픈 건 없어 | gold: 운동 시 호흡곤란 | top5: 가슴 답답, 호흡곤란, 흉통, 운동 시 호흡곤란, 가슴 두근거림 | negative: 흉통 | negative@5: 흉통
- `train_bp_044` Q1 kangwon | text: 약을 삼키려면 목에 걸린 듯 잘 안 넘어가는데 목이 아픈 건 아녀 | gold: 삼키기 곤란 | top5: 삼키기 곤란, 목의 통증, 근력 약화, 가래, 목소리 변화 | negative: 목의 통증 | negative@5: 목의 통증
- `train_bp_046` Q1 kangwon | text: 심장이 너무 빨리 뛰는 느낌인데 가심이 아픈 건 없어 | gold: 빈맥 | top5: 빈맥, 가슴 두근거림, 가슴 답답, 흉통, 눈이 무거운 느낌 | negative: 흉통 | negative@5: 흉통
- `train_bp_049` Q1 kangwon | text: 설사를 자꾸 하는데 토하는 건 아녀 | gold: 설사 | top5: 설사, 구토, 발한, 피로감, 결막염 | negative: 구토 | negative@5: 구토
- `train_bp_059` Q3 standard | text: 숨쉴 때 쌕쌕 소리가 나는데 숨이 막히는 느낌은 없어 | gold: 천명음 | top5: 천명음, 가슴 답답, 결막염, 호흡곤란, 흉통 | negative: 호흡곤란 | negative@5: 호흡곤란
- `train_bp_062` Q3 standard | text: 가슴이 아픈 건 괜찮아졌는데 답답한 건 아직 남아 | gold: 가슴 답답 | top5: 가슴 답답, 흉통, 가슴 두근거림, 함몰가슴, 목의 통증 | negative: 흉통 | negative@5: 흉통
- `train_bp_067` Q3 standard | text: 입맛이 너무 없는데 토하진 않아 | gold: 식욕부진 | top5: 빈맥, 식욕부진, 구토, 호흡곤란 | negative: 구토 | negative@5: 구토
- `train_bp_074` Q3 standard | text: 약 먹고 속이 울렁거려서 토했는데 설사는 없어 | gold: 구토 | top5: 구토, 설사, 피로감 | negative: 설사 | negative@5: 설사
- `train_bp_076` Q3 kangwon | text: 기침은 좀 나았는데 목은 아직 칼칼하니 아퍼 | gold: 목의 통증 | top5: 가슴 답답, 목의 통증, 기침, 결막염, 체중감소 | negative: 기침 | negative@5: 기침
- `train_bp_082` Q3 kangwon | text: 기침은 좀 줄었는데 가래가 아직 끼어 있어 | gold: 가래 | top5: 가래, 검은색 가래, 기침, 화농성 객담, 거품이 섞인 가래 | negative: 기침 | negative@5: 기침
- `train_bp_099` Q3 kangwon | text: 배가 빵빵허긴 한데 아픈 건 아녀 | gold: 복부팽만감 | top5: 복부팽만감, 복부 통증, 흉통, 탈장, 가슴 답답 | negative: 복부 통증 | negative@5: 복부 통증

## Alias Miss Samples

- `train_bp_017` Q1 standard | text: 몸살 난 것처럼 온몸이 쑤시고 열도 나 | gold: 근육통, 열 | top5: 근육통, 온몸이 떨림, 가슴 답답, 오한, 열 | alias_miss: 열
- `train_bp_030` Q1 kangwon | text: 열은 좀 나는데 기침은 안 나와 | gold: 열 | top5: 목소리 변화, 삼키기 곤란, 근력 약화, 가래, 천명음 | alias_miss: 열
- `train_bp_040` Q1 kangwon | text: 기침하고 나면 가래에 피가 살짝 비쳐 | gold: 객혈 | top5: 객혈, 가래, 기침, 검은색 가래, 권태감 | alias_miss: 객혈
- `train_bp_054` Q3 standard | text: 약 먹고 좀 괜찮다가 어제부터 열이 다시 나 | gold: 열 | top5: 열, 빈맥, 빈호흡, 사망, 기침 | alias_miss: 열
- `train_bp_062` Q3 standard | text: 가슴이 아픈 건 괜찮아졌는데 답답한 건 아직 남아 | gold: 가슴 답답 | top5: 가슴 답답, 흉통, 가슴 두근거림, 함몰가슴, 목의 통증 | alias_miss: 가슴 답답
- `train_bp_064` Q3 standard | text: 약은 먹었는데도 몸에 힘이 계속 없어 | gold: 기운없음 | top5: 코막힘, 근력 약화, 콧물, 기운없음, 감기 증상 | alias_miss: 기운없음
- `train_bp_077` Q3 kangwon | text: 코가 아직도 맥혀서 답답해 | gold: 코막힘 | top5: 코막힘, 가슴 답답, 복부 통증 | alias_miss: 코막힘
- `train_bp_087` Q3 kangwon | text: 가심이 새로 아픈데 숨찬 건 아녀 | gold: 흉통 | top5: 가슴 답답, 흉통 | alias_miss: 흉통
- `train_bp_097` Q3 kangwon | text: 손발이 전보다 부어서 퉁퉁해 | gold: 사지 부종 | top5: 사지 부종, 하지부종, 목소리 변화, 두통, 근육통 | alias_miss: 사지 부종

## Top1 Not Gold Samples

- `train_bp_003` Q1 standard | text: 열은 나는데 춥거나 몸이 떨리는 건 없어 | gold: 열 | top5: 온몸이 떨림, 오한, 감기 증상, 삼키기 곤란, 가슴 답답
- `train_bp_007` Q1 standard | text: 기침이 계속 나와서 왔어 | gold: 기침 | top5: 콧물, 코막힘, 결막염, 삼키기 곤란, 가슴 답답
- `train_bp_009` Q1 standard | text: 기침할 때마다 가래가 같이 나와 | gold: 가래, 기침 | top5: 검은색 가래, 가래, 기침, 화농성 객담, 목소리 변화
- `train_bp_011` Q1 standard | text: 가래가 까맣게 섞여 나와서 걱정돼 | gold: 검은색 가래 | top5: 가래, 기침, 검은색 가래, 객혈, 거품이 섞인 가래
- `train_bp_020` Q1 standard | text: 물 마실 때 자꾸 사레가 들리는데 음식이 안 넘어가진 않아 | gold: 사래걸림 | top5: 삼키기 곤란, 천명음, 설사, 가슴 답답, 발한
- `train_bp_028` Q1 kangwon | text: 코물이 자꾸 흘러서 훌쩍거리게 돼 | gold: 콧물 | top5: 설사, 콧물, 발한, 재채기, 가슴 답답
- `train_bp_030` Q1 kangwon | text: 열은 좀 나는데 기침은 안 나와 | gold: 열 | top5: 목소리 변화, 삼키기 곤란, 근력 약화, 가래, 천명음
- `train_bp_036` Q1 kangwon | text: 숨쉴 때 가슴에서 쌕쌕 소리가 나 | gold: 천명음 | top5: 가슴 답답, 천명음, 흉통, 결막염, 콧물
- `train_bp_037` Q1 kangwon | text: 조금만 움직여도 숨이 벅차서 힘들어 | gold: 호흡곤란 | top5: 운동 시 호흡곤란, 호흡곤란, 가슴 답답, 가래, 복벽이 움푹 들어감
- `train_bp_038` Q1 kangwon | text: 계단만 올라가도 숨이 차는데 가슴이 아픈 건 없어 | gold: 운동 시 호흡곤란 | top5: 가슴 답답, 호흡곤란, 흉통, 운동 시 호흡곤란, 가슴 두근거림
- `train_bp_052` Q3 standard | text: 열은 다 내렸는데 콧물이 계속 나와 | gold: 콧물 | top5: 재채기, 코막힘, 목소리 변화, 콧물, 감기 증상
- `train_bp_056` Q3 standard | text: 열은 이제 없는데 기침이 계속 남아 있어 | gold: 기침 | top5: 콧물, 코막힘, 결막염, 삼키기 곤란, 가슴 답답
- `train_bp_060` Q3 standard | text: 진료 이후로 조금만 걸어도 숨이 차기 시작했어 | gold: 호흡곤란 | top5: 운동 시 호흡곤란, 호흡곤란, 가슴 답답, 흉통, 무증상
- `train_bp_064` Q3 standard | text: 약은 먹었는데도 몸에 힘이 계속 없어 | gold: 기운없음 | top5: 코막힘, 근력 약화, 콧물, 기운없음, 감기 증상
- `train_bp_067` Q3 standard | text: 입맛이 너무 없는데 토하진 않아 | gold: 식욕부진 | top5: 빈맥, 식욕부진, 구토, 호흡곤란
- `train_bp_070` Q3 standard | text: 물을 마실 때마다 자꾸 사레가 들어 | gold: 사래걸림 | top5: 설사, 복벽이 움푹 들어감, 근력 약화, 천명음, 발한
- `train_bp_076` Q3 kangwon | text: 기침은 좀 나았는데 목은 아직 칼칼하니 아퍼 | gold: 목의 통증 | top5: 가슴 답답, 목의 통증, 기침, 결막염, 체중감소
- `train_bp_086` Q3 kangwon | text: 걸을 때마다 숨이 벅차게 차기 시작했어 | gold: 운동 시 호흡곤란 | top5: 호흡곤란, 가슴 답답, 흉통, 운동 시 호흡곤란, 무증상
- `train_bp_087` Q3 kangwon | text: 가심이 새로 아픈데 숨찬 건 아녀 | gold: 흉통 | top5: 가슴 답답, 흉통
- `train_bp_090` Q3 kangwon | text: 며칠 전부터 몸살처럼 온몸이 쑤시기 시작했어 | gold: 근육통 | top5: 온몸이 떨림, 근육통, 흉통, 무증상, 감기 증상
