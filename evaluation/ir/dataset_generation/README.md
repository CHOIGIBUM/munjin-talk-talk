# Synthetic IR Dataset Generation

This folder contains the public synthetic data generation pipeline for MunjinTalkTalk IR evaluation.

The generated cases are not real patient data.  The seed file is the public 100-case development dataset, used only to collect the allowed symptom label vocabulary and preserve the approximate evaluation distribution.

## Why This Exists

The original 100 cases are useful for development, but once failures are inspected and aliases/few-shots are improved, that set becomes a tuning set.  The generated 1000-case set is also public development/regression data once its failures have been inspected.  A true blind benchmark must be generated after code, prompt, alias, and few-shot files are frozen.

| Split | Count | Intended use |
| --- | ---: | --- |
| `dev` | 300 | Alias/few-shot/domain-pack tuning is allowed |
| `validation` | 200 | Midpoint checks; avoid using individual misses as direct rules |
| `locked_holdout` | 500 | Historical holdout split; final only if it has not been inspected |

## Design

The generator first creates a 1000-row blueprint, then renders patient-style Korean utterances from that blueprint.

Controlled dimensions:

- visit type: 600 initial, 400 follow-up
- question mix: Q1 810, Q3 190
- question type mix: chief complaint 540, medication context 60, progress 270, new symptoms 130
- dialect mix: 500 standard, 500 colloquial/dialect-style
- difficulty mix: 400 easy, 400 medium, 200 hard
- symptom coverage: 47 gold symptom labels from the public seed set
- multi-symptom cases: 400
- negative/absent symptom context: 250

The renderer keeps the main utterance symptom-focused and uses casual spoken
Korean rather than formal `-습니다` style.  Dialect cases also receive selected
surface forms from `backend/serverless/src/data/dialect_packs/dialect_kangwon.csv`
so the synthetic data exercises the same dialect RAG vocabulary used by the
runtime.  If an exact duplicate text is detected, the validator appends a short
natural context phrase to that duplicate only.

## Generate

From the repository root:

```powershell
python evaluation\ir\dataset_generation\generate_synthetic_ir_dataset.py
```

Outputs are written to:

```text
evaluation/ir/data/synthetic/
```

Main files:

| File | Purpose |
| --- | --- |
| `blueprint_1000.json` | The fixed case design before text rendering |
| `synthetic_1000.json` | Full generated dataset |
| `synthetic_dev_300.json` | Tuning split |
| `synthetic_validation_200.json` | Validation split |
| `synthetic_locked_holdout_500.json` | Historical holdout split |
| `synthetic_summary.json` | Distribution summary |
| `validation_summary_1000.json` | Output from `validate_eval_data.py` |

## Validate

```powershell
python evaluation\ir\validate_eval_data.py `
  --input evaluation\ir\data\synthetic\synthetic_1000.json `
  --summary-output evaluation\ir\data\synthetic\validation_summary_1000.json
```

Validate each split:

```powershell
python evaluation\ir\validate_eval_data.py --input evaluation\ir\data\synthetic\synthetic_dev_300.json
python evaluation\ir\validate_eval_data.py --input evaluation\ir\data\synthetic\synthetic_validation_200.json
python evaluation\ir\validate_eval_data.py --input evaluation\ir\data\synthetic\synthetic_locked_holdout_500.json
```

## Reporting Rule

When reporting model quality:

- Use the original 100 cases and `synthetic_dev_300` as development data.
- Use `synthetic_validation_200` for sanity checks.
- Use `synthetic_locked_holdout_500` only for final reporting.
- If the holdout failures are inspected and used to change aliases, prompts, few-shots, or rules, create a new locked holdout before claiming final performance.
