# Research Design

This document records the clean evaluation order for MunjinTalkTalk symptom IR/RAG development.

## Core Principle

Training data and held-out test data must have different roles.

- `train_100`: build and inspect runtime artifacts.
- `test_1000`: measure held-out generalization.

Do not use `test_1000` failures to revise aliases, few-shots, domain packs, prompts, or scoring rules before saving the first evaluation report.

## Data Roles

| Dataset | Size | Role | Can Improve Runtime? | Can Report Generalization? |
| --- | ---: | --- | --- | --- |
| `train_100` | 100 | Build domain pack, aliases, few-shot candidates, and sanity-check retrieval | Yes | No |
| `test_1000` | 1000 | Held-out evaluation after runtime freeze | No, before first report | Yes |

## Current Research Sequence

1. Reset contaminated evaluation and IR artifacts.
2. Design `train_100` blueprint.
3. Render `train_100` with LLM-generated patient utterances.
4. Build runtime artifacts only from accepted `train_100`.
5. Run train sanity evaluation to catch obvious candidate-search failures.
6. Add provenance metadata, including dialect source layers.
7. Freeze train-derived runtime artifacts.
8. Design `test_1000` blueprint with held-out controls.
9. Render `test_1000` without using train utterances as examples.
10. Run quality gates before evaluation.
11. Run the first held-out evaluation once.
12. Save aggregate metrics and case-level outputs.
13. Only then inspect failures and plan post-test iteration.

## Evaluation Layers

### Candidate Retrieval

Measures whether the correct canonical symptoms appear in deterministic candidate lists.

Primary metrics:

- recall@1, recall@3, recall@5, recall@10
- all-gold-hit@5
- top1 case accuracy
- negative-in-top5

### Alias And Dialect Hints

Measures whether colloquial, dialectal, or paraphrased expressions are recognized as hints.

Important distinction:

- Active alias hit: can support a current symptom.
- Inactive alias marker: identifies denied, absent, resolved, or improved symptoms and should not become a current symptom.

### LLM Extraction

Measures whether the pipeline uses transcript-grounded spans and does not hallucinate symptoms from RAG context.

Primary checks:

- source_quote grounded in patient text
- correct status: `있음`, `없음`, `확인필요`
- no Q2/Q4 leakage into Q1/Q3 evaluation
- no current symptom card for denied symptoms

## Dialect Design

Dialect must be reported by source layer:

| Layer | Meaning |
| --- | --- |
| `none` | Standard Korean |
| `rag_pack_anchored` | Uses expressions directly grounded in the current Gangwon dialect pack |
| `train_validated_medical_colloquial` | Uses medical colloquial forms validated in train data, not necessarily in the dialect pack |
| `light_dialect_flavor` | Lightly local or colloquial cadence without a strong dialect-pack anchor |

This prevents the false claim that every Kangwon-labeled utterance is backed by the current dialect RAG pack.

## Reporting Rule

Use separate wording:

- Train sanity result: "internal check on train-derived artifacts."
- Test result: "held-out evaluation."

Never present `train_100` metrics as final model performance.
