# 문진톡톡 백엔드 런타임 데이터 자산 안내

이 폴더(`src/data/`)는 문진톡톡 백엔드의 **AI 추론(LangGraph), 방언 해독(RAG), 표준 증상 매칭(Hybrid IR)** 파이프라인이 런타임에 참조하는 핵심 데이터들의 저장소입니다.

본 프로젝트는 오픈소스 코드의 투명성과 원천 의료 데이터의 저작권 보호를 양립시키기 위해 철저한 **이원화 데이터 거버넌스 정책**을 적용하고 있습니다.

---

## 💡 데이터 거버넌스 원칙

1. **공개 대상 (설정 및 규칙 자산):** 서비스의 구조, 프롬프트 로직, 질문 흐름을 검증할 수 있는 설정 파일은 100% 공개합니다.
2. **비공개 대상 (핵심 의료 자산):** 서울아산병원 질병백과를 기반으로 정제된 원천 텍스트, 파생 증상 인덱스, 임베딩 캐시는 저작권 및 라이선스 준수를 위해 본 공개 저장소에서 제외합니다.

> **심사 및 검토 안내:** > 공개 레포지토리 클론만으로도 백엔드 빌드, 파이프라인 정합성 테스트, 기본 문진 로직 검토가 완벽하게 가능합니다. 단, 운영 수준의 '정밀 표준 증상 매칭(Hybrid IR)'을 직접 실행 및 시연하시려면 하단의 안내에 따라 비공개 런타임 데이터를 별도로 배치해야 합니다.

---

## 1. 공개 저장소에 포함되는 파일

| 파일 경로 | 자산 구분 | 임상 및 파이프라인 역할 |
| --- | --- | --- |
| `domain_packs/respiratory.json` | 도메인 규칙 | 호흡기 외래 특화 문진 규격, 상태값(Enum), 안전 플래그 트리거 기준 정의 |
| `fewshots/respiratory/*.json` | LLM Few-shot | 추론 단계별 답변 구조화 템플릿 및 프롬프트 회귀 테스트 기준값 |
| `dialect_packs/dialect_kangwon.json` | 사투리 RAG | 강원 지역 방언("고달프다", "매자지다" 등)을 표준 의학 용어로 매핑하는 시드 |
| `dialect_packs/dialect_kangwon.csv` | 원본 관리 | 사투리 팩의 사전 편집 및 기획자 검토용 CSV 마스터 파일 |
| `question_sets/default.json` | 문진 세트 | 프론트엔드 태블릿 UI와 백엔드 세션을 동기화하는 Q1~Q4 질문 명세 |
| `domain_packs/respiratory_fewshot.txt` | 레거시 | 구버전 텍스트 기반 Few-shot 예시 *(현재는 `fewshots/` JSON으로 대체됨)* |

---

## 2. 공개 저장소에서 제외된 파일 (비공개 런타임)

아래 3개 파일은 Git 트래킹에서 제외되어 있으며, 서버리스 Lambda가 정상적인 IR 검색을 수행하기 위한 필수 전제 조건입니다.

| 파일명 | 원천 소스 | 부재 시 시스템 영향도 |
| --- | --- | --- |
| `diseases_cleaned.json` | 서울아산병원 질병백과 | 질환 본문 검색 불가 (IR 후보 생성 실패) |
| `symptom_index.json` | 파생 인덱스 | 표준 증상명 $\leftrightarrow$ 질환 간의 역색인 매핑 불가 |
| `symptom_embeddings_*.json` | Titan Embeddings v2 | 의미론적 유사도 기반의 Vector Search 비활성화 |

---

## 3. 배포 전 데이터 주입 가이드

팀 내부 비공개 저장소에서 핵심 데이터 3종을 다운로드하여 아래의 디렉터리 트리 형태로 배치합니다.

```text
backend/serverless/src/data/
├── diseases_cleaned.json                     # [비공개 주입 필수]
├── symptom_index.json                        # [비공개 주입 필수]
├── symptom_embeddings_amazon.titan...json    # [비공개 주입 필수]
├── dialect_packs/
├── domain_packs/
└── question_sets/
```

**주입 완료 확인 (PowerShell):**

```powershell
cd backend/serverless/src/data
Get-Item diseases_cleaned.json, symptom_index.json, symptom_embeddings_*.json
```
*(에러 없이 3개 파일의 정보가 모두 출력되어야 준비가 완료된 것입니다.)*

---

## 4. 실수 방지를 위한 Git 안전 점검

로컬에 주입한 비공개 데이터가 원격 저장소에 유출되지 않도록 커밋 전 상태를 반드시 확인합니다.

```powershell
git status --short --ignored -- backend/serverless/src/data
```

* **`!!` 로 표시될 때:** `.gitignore`에 의해 정상적으로 차단되고 있음 (**안전**)
* **`??` 로 표시될 때:** Git 추적 리스트에 노출됨 (**즉시 커밋 중단 및 `.gitignore` 재확인 필요**)

---

## 5. 백엔드 내부 모듈의 데이터 소비 구조

백엔드 구동 시 각 내부 모듈은 본 폴더의 자산을 다음과 같은 연결 고리로 참조합니다.

* `question_sets.py` $\rightarrow$ `question_sets/default.json` 로드
* `domain_config.py` $\rightarrow$ `domain_packs/{DOMAIN_PACK}.json` 로드
* `fewshots.py` $\rightarrow$ `fewshots/{DOMAIN_PACK}/*.json` 로드
* `dialect_rag.py` $\rightarrow$ `dialect_packs/{DIALECT_PACK}.json` 로드
* `retrieval.py` $\rightarrow$ 주입된 **비공개 IR 데이터 3종** (`diseases_cleaned`, `symptom_index`, `embeddings`) 로드
