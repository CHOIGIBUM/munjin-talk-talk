# 런타임 데이터 배치 안내

이 폴더는 문진톡톡 백엔드가 질문셋, 도메인 설정, 방언 RAG, 표준 증상 IR을 수행할 때 참조하는 데이터 위치입니다.

공개 GitHub에는 코드와 공개 가능한 설정 파일만 포함합니다. 저작권 또는 이용 범위 검토가 필요한 원천 의료 백과 데이터, 그 파생 증상 인덱스, embedding cache는 공개 저장소에 포함하지 않습니다.

`test/add-coverage` 브랜치에서 이 문서는 테스트 실행 전 데이터 의존성을 확인하는 기준입니다. 로컬 단위 테스트 중 일부는 비공개 IR 원천 데이터가 없어도 fallback 또는 skip으로 동작하지만, 실제 운영 수준의 Hybrid IR 평가와 AWS 통합 테스트는 런타임 데이터 배치 상태의 영향을 받습니다.

---

## 1. 공개 저장소에 포함되는 파일

| 경로 | 용도 |
| --- | --- |
| `domain_packs/respiratory.json` | 호흡기 문진 도메인 설정, status enum 설명, 안전 플래그 기준 |
| `domain_packs/respiratory_fewshot.txt` | 일반화된 extraction few-shot 예시 |
| `dialect_packs/dialect_kangwon.json` | 강원 방언 표현을 표준어 후보로 연결하는 RAG 참조 데이터 |
| `dialect_packs/dialect_kangwon.csv` | 방언팩 원본 관리용 표 데이터 |
| `question_sets/default.json` | 초진/재진 문진 질문 세트 |
| `README.md` | 현재 문서 |

이 파일들은 서비스 구조와 프롬프트/질문셋을 이해하는 데 필요하므로 공개합니다.

## 1-1. 테스트와의 관계

테스트 계층별로 이 폴더를 참조하는 방식이 다릅니다.

| 테스트/평가 | 데이터 의존성 |
| --- | --- |
| `backend/serverless/tests/test_question_sets.py` | `question_sets/default.json` 구조 확인 |
| `backend/serverless/tests/test_dialect_rag.py` | `dialect_packs/dialect_kangwon.json` 로드와 RAG context shape 확인 |
| `backend/serverless/tests/test_ir_noise_and_safety.py` | 비공개 IR 데이터가 없으면 일부 항목은 skip 또는 domain pack fallback 확인 |
| `evaluation/ir/` | 실제 표준 증상 후보 검색 성능을 보려면 `symptom_index.json`과 embedding cache 필요 |
| `tests/aws/test_aws_full.py` | 배포된 Lambda 환경에 런타임 데이터가 포함되어 있는지 간접 확인 |

따라서 "로컬 테스트가 일부 통과한다"와 "운영 수준의 IR 매칭이 완전하게 동작한다"는 같은 의미가 아닙니다. 해커톤 제출에서는 이 구분을 분명히 하는 것이 좋습니다.

---

## 2. 공개 저장소에 포함하지 않는 파일

| 파일 | 용도 | 제외 이유 |
| --- | --- | --- |
| `diseases_cleaned.json` | 질환 백과 원천 정리본 | 원천 본문과 파생 데이터의 공개 범위 검토 필요 |
| `symptom_index.json` | 표준 증상명과 질환 문서 연결 인덱스 | 원천 데이터 기반 파생 인덱스 |
| `symptom_embeddings_amazon.titan-embed-text-v2_0_512.json` | Titan embedding cache | 원천 증상 문서 기반 파생 벡터 |

이 세 파일이 없으면 백엔드 실행 자체는 가능하더라도 Hybrid IR 표준 증상 매칭은 정상 성능으로 동작하지 않습니다.

---

## 3. 배포 전 배치해야 하는 구조

팀 내부 비공개 저장소나 로컬 보관 위치에서 아래 파일을 복사해 넣습니다.

```text
backend/serverless/src/data/
  diseases_cleaned.json
  symptom_index.json
  symptom_embeddings_amazon.titan-embed-text-v2_0_512.json
  domain_packs/
  dialect_packs/
  question_sets/
```

PowerShell 확인:

```powershell
cd backend/serverless/src/data
Get-Item diseases_cleaned.json
Get-Item symptom_index.json
Get-Item symptom_embeddings_amazon.titan-embed-text-v2_0_512.json
```

---

## 4. Git 관리 기준

`.gitignore`에는 위 3개 비공개 런타임 데이터가 다시 올라가지 않도록 패턴이 등록되어 있어야 합니다.

```text
backend/serverless/src/data/diseases_cleaned.json
backend/serverless/src/data/symptom_index.json
backend/serverless/src/data/symptom_embeddings_*.json
```

커밋 전 확인:

```powershell
git status --short --ignored -- backend/serverless/src/data
```

비공개 파일이 `!!`로 보이면 Git에서 무시되고 있는 상태입니다. `??`로 보이면 `.gitignore`가 빠진 것이므로 커밋하면 안 됩니다.

---

## 5. 서비스 내 참조 방식

- 질문 세트는 `question_sets.py`가 `question_sets/default.json`을 읽습니다.
- 도메인 설정과 few-shot은 `domain_config.py`가 `domain_packs/`에서 읽습니다.
- 방언 RAG는 `dialect_rag.py`가 `dialect_packs/dialect_kangwon.json`을 읽습니다.
- 표준 증상 IR은 `retrieval_documents.py`, `retrieval_embeddings.py`, `retrieval.py`가 비공개 3개 파일을 읽습니다.

따라서 공개 저장소 clone만으로는 코드 구조 검토와 기본 빌드는 가능하지만, 실제 운영 수준의 증상 매칭은 비공개 런타임 데이터 배치 후 확인해야 합니다.
