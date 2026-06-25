# Public Synthetic IR Dataset

This directory contains a 1000-case synthetic evaluation dataset for MunjinTalkTalk symptom IR/linking.

The cases are synthetic and contain no real patient data.  They are generated from the pipeline in `evaluation/ir/dataset_generation/`.

## Files

| File | Count | Use |
| --- | ---: | --- |
| `synthetic_1000.json` | 1000 | Full synthetic set |
| `synthetic_dev_300.json` | 300 | Tuning and error analysis |
| `synthetic_validation_200.json` | 200 | Intermediate validation |
| `synthetic_locked_holdout_500.json` | 500 | Final reporting only |
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
- 400 multi-symptom cases
- 250 cases with negative/absent symptom context

## Holdout Policy

Do not use `synthetic_locked_holdout_500.json` to add aliases, rules, or few-shots.  If holdout failures are inspected for tuning, generate a fresh locked holdout before reporting final performance.
