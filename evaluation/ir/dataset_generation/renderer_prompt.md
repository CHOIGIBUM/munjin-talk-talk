# LLM Renderer Prompt Template

Use this template when rendering blueprint rows into patient utterances.

```text
You are generating synthetic Korean patient utterances for a symptom IR benchmark.

The output is not real patient data. Generate only the patient's answer text.

Input fields:
- visit_type: {visit_type}
- question_id: {question_id}
- dialect_type: {dialect_type}
- gold_symptoms: {gold_symptoms}
- negative_symptoms: {negative_symptoms}
- expression_policy: {expression_policy}
- difficulty: {difficulty}
- generation_notes: {generation_notes}

Rules:
1. Write in casual spoken Korean. Do not use formal -습니다/-합니다 style.
2. If dialect_type is kangwon, use natural Gangwon-style colloquial wording based on the dialect reference. Do not overuse rare dialect words.
3. Preserve the meaning of every gold_symptom.
4. Do not add extra symptoms that are not in gold_symptoms unless they are explicitly in negative_symptoms as denied/absent context.
5. If expression_policy is direct_allowed, common symptom names may appear directly.
6. If expression_policy is lay_preferred, prefer everyday phrasing over clinical labels.
7. If expression_policy is direct_label_forbidden, do not include the exact standard symptom label in the utterance.
8. For 초진 Q1, answer the current chief complaint.
9. For 재진 Q3, answer follow-up course, persistence, recurrence, worsening, improvement, or medication-related symptom course.
10. Output only one utterance string. No bullet points, no explanation, no JSON.
```
