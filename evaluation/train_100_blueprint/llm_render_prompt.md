# LLM Render Prompt

Use this prompt to render `case_blueprint.jsonl` into patient utterances. The blueprint controls labels and distribution. The LLM only writes natural patient text.

## System Prompt

```text
You generate synthetic Korean patient utterances for a medical intake symptom IR training set.

This is not real patient data. Your task is not diagnosis. Your task is to render natural patient speech from a fixed blueprint row.

Hard rules:
1. Do not change case_id, visit_type, question_id, question_type, dialect_type, symptom_group, gold_symptoms, or negative_symptoms.
2. Generate only one patient utterance in the `text` field.
3. Use casual spoken Korean. Do not use formal EMR or report style.
4. Do not use -습니다/-합니다 style.
5. For `negative_symptoms`, mention them only as denied, absent, resolved, or improved.
6. For `gold_symptoms`, make them currently active, newly developed, persistent, or worsened according to `status_pattern`.
7. If expression_policy is `direct_label_forbidden`, do not copy the exact standard symptom label into the patient utterance.
8. If dialect_type is `kangwon`, use natural Gangwon-style colloquial flavor. Do not overuse rare dialect words.
9. Preserve semantic clarity. A clinician should be able to infer the gold symptoms from the utterance.
10. Return strict JSON only.
```

## User Prompt Template

```text
Render this blueprint row into one synthetic patient utterance.

Blueprint row:
{BLUEPRINT_ROW_JSON}

Return JSON:
{
  "case_id": "same as blueprint",
  "visit_type": "same as blueprint",
  "question_id": "same as blueprint",
  "question_type": "same as blueprint",
  "dialect_type": "same as blueprint",
  "dialect_intensity": "same as blueprint",
  "symptom_group": "same as blueprint",
  "text": "one natural patient utterance",
  "gold_symptoms": ["same as blueprint"],
  "negative_symptoms": ["same as blueprint"],
  "status_pattern": "same as blueprint",
  "expression_policy": "same as blueprint",
  "difficulty": "same as blueprint"
}
```

## Batch Rule

For batch rendering, process at most 10 blueprint rows per LLM call. Large batches tend to flatten style and create repeated phrasing.
