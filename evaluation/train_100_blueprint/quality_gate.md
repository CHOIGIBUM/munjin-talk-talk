# Train 100 Quality Gate

Accept a rendered case only when all checks pass.

## Structural Checks

- Exactly 100 cases.
- Every `case_id` in `case_blueprint.jsonl` appears once.
- No extra case IDs.
- All metadata fields match the blueprint exactly.
- `text` is non-empty.
- No duplicate `text`.

## Distribution Checks

- 초진 Q1: 50.
- 재진 Q3: 50.
- Standard colloquial: 50.
- Kangwon colloquial: 50.
- Quadrants are 25 each.
- Symptom group counts match `distribution_plan.json`.
- `dialect_source_layer` counts match `distribution_plan.json`.
- Standard rows have `dialect_source_layer: none`.
- Kangwon rows are interpreted by source layer, not assumed to be entirely dialect-RAG-grounded.

## Leakage Checks

- `direct_label_forbidden` cases must not contain exact forbidden standard labels.
- Patient text must not be EMR style.
- Patient text must not contain JSON, bullets, diagnosis, or explanation.
- Test data must not be used to revise this training set.

## Semantic Checks

- Every `gold_symptoms` item is supported by the patient text.
- Every `negative_symptoms` item is absent, denied, resolved, or improved.
- Q1 cases answer chief complaint.
- Q3 cases answer new symptoms or post-visit course.
- Kangwon cases remain understandable and do not become rare-word dumps.

## Use After Acceptance

Accepted `train_100` may be used to create:

- domain pack candidates
- alias candidates
- few-shot candidates

Each derived item must record the supporting `case_id`.
