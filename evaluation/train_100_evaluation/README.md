# Train 100 Offline Evaluation

This folder evaluates the runtime IR/RAG artifacts built from `train_100`.

Important: this is a training-set sanity evaluation, not held-out performance.
It checks whether the rebuilt domain pack, aliases, and BM25 candidate search can
cover the 100 training cases before a separate locked test set is created.

## Command

```powershell
cd C:\Users\CGB\munjin-talk-talk-mvp
python evaluation\train_100_evaluation\evaluate_offline_ir.py
```

## Outputs

- `evaluation/train_100_evaluation/offline_ir_results.json`
- `evaluation/train_100_evaluation/case_analysis.md`

