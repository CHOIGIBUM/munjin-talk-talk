# Train 100 v2 Rendered Data

이 폴더는 `blueprint/case_blueprint.jsonl`에서 생성한 100개 synthetic 환자 발화와, 그 데이터를 이용해 런타임 후보 검색 보조 산출물을 만드는 스크립트를 담습니다.

이 데이터는 학습/점검용입니다. Held-out 성능으로 보고하면 안 됩니다.

## 파일

- `train_100_v2.jsonl`: 렌더링된 환자 발화 100개입니다.
- `quality_gate_report.json`: 렌더링 데이터 검증 요약입니다.
- `render_train.py`: Bedrock 기반 렌더링 스크립트입니다.
- `build_artifacts.py`: ontology와 `train_100_v2`를 이용해 domain pack/few-shot 후보를 만드는 스크립트입니다.
- `artifact_build_report.json`: 생성 산출물 개수와 분포 검증 요약입니다.

상세 provenance와 실행별 raw output은 커밋하지 않습니다.

## 런타임 산출물 생성

프로젝트 루트에서 실행합니다.

```powershell
python -X utf8 evaluation\hybrid_ir_pipeline\train_100_v2\build_artifacts.py
```

builder는 다음 파일을 갱신할 수 있습니다.

- `backend/serverless/src/data/domain_packs/respiratory.json`
- `backend/serverless/src/data/fewshots/respiratory/*.json`

`backend/serverless/src/data/symptom_index.json`을 제품 ontology source로 사용하고, `train_100_v2.jsonl`은 alias, quote-pattern, few-shot 후보 보조 자료로만 사용합니다.
