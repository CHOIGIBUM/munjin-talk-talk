# Derived IR Knowledge

This directory is for alias and few-shot proposals derived from `data/generated/train_100/cases.json`.

Files in this directory should be reviewable and explainable:

```text
alias_proposals.train100.json
fewshot_proposals.train100.json
```

Each proposal should include:

- the suggested alias or few-shot
- the target symptom label
- the training case IDs that motivated it
- a short reason
- whether it has been promoted into backend runtime data

Do not derive proposals from `test_1000` failures.
