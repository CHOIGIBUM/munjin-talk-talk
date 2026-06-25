# Public Synthetic IR Regression Dataset

This directory contains a 1000-case synthetic regression dataset for MunjinTalkTalk symptom IR/linking.

The cases are synthetic and contain no real patient data.  They are generated from the pipeline in `evaluation/ir/dataset_generation/`.
This dataset has already been inspected during alias/few-shot development, so it must not be reported as a blind benchmark.

## Files

| File | Count | Use |
| --- | ---: | --- |
| `synthetic_1000.json` | 1000 | Full public regression set |
| `synthetic_dev_300.json` | 300 | Tuning and error analysis |
| `synthetic_validation_200.json` | 200 | Historical validation split; not blind after inspection |
| `synthetic_locked_holdout_500.json` | 500 | Historical holdout split; not blind after inspection |
| `blueprint_1000.json` | 1000 | Generation blueprint |
| `synthetic_summary.json` | - | Distribution summary |
| `validation_summary_1000.json` | - | Validator summary |

## Current Summary

- 1000 cases
- 600 initial, 400 follow-up
- 810 Q1, 190 Q3
- 500 standard, 500 dialect/colloquial-style
- 400 easy, 400 medium, 200 hard
- 47 unique gold symptoms
- each gold symptom appears 31-33 times
- 400 multi-symptom cases
- 250 cases with negative/absent symptom context

## Blind Evaluation Policy

Use this 1000-case set for public development, regression checks, and distribution sanity checks only.

For a clean final score:

1. Freeze prompts, few-shots, aliases, and matcher code.
2. Generate a fresh holdout after the freeze.
3. Do not inspect individual fresh-holdout failures before reporting.
4. Report end-to-end F1 separately from candidate-only Recall@k.
