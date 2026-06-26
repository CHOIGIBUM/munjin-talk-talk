# Train 100 Blueprint

This folder defines the first clean training dataset for rebuilding MunjinTalkTalk symptom IR/domain knowledge.

The important rule is that this folder does not generate final patient utterances with code. It defines a case-level blueprint. The actual `text` field must be rendered by an LLM from `case_blueprint.jsonl` using `llm_render_prompt.md`.

## Files

| File | Purpose |
| --- | --- |
| `distribution_plan.json` | Target distribution for the 100 training cases |
| `case_blueprint.jsonl` | 100 row blueprint without patient utterances |
| `case_blueprint.schema.json` | JSON schema for each blueprint row |
| `llm_render_prompt.md` | Prompt template for LLM-based utterance rendering |
| `quality_gate.md` | Manual and automated checks before accepting rendered data |
| `dialect_source_policy.md` | Clarifies whether Kangwon rows are RAG-pack anchored, medical colloquial, or light dialect flavor |

## Workflow

1. Review `distribution_plan.json`.
2. Review `case_blueprint.jsonl`.
3. Render patient utterances with an LLM using `llm_render_prompt.md`.
4. Save rendered output as `evaluation/generated/train_100/cases.jsonl`.
5. Validate that each rendered case keeps the exact blueprint labels.
6. Use only this accepted `train_100` to derive aliases, few-shots, and domain-pack candidates.

No `test_1000` cases should be generated until the train-derived runtime artifacts are frozen.

## Dialect Note

The 50 Kangwon-labeled training rows are not all grounded in the current Gangwon dialect RAG pack. They now carry a `dialect_source_layer` field so later reporting can distinguish standard rows, actual dialect-pack anchored rows, train-validated medical colloquial rows, and light dialect-flavored rows.
