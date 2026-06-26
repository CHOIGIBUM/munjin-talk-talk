# Evaluation Reset

The previous IR evaluation folder, generated datasets, run outputs, hand-built aliases, few-shots, and domain-pack-derived tuning artifacts have been removed.

This directory is intentionally empty except for this reset marker. The next evaluation pipeline should be rebuilt from a documented design in this folder.

Planned rebuild order:

1. Define the data generation blueprint and leakage rules.
2. Generate `train_100`.
3. Build domain pack, aliases, and few-shot candidates from `train_100` only.
4. Freeze those runtime artifacts.
5. Generate a separate locked `test_1000`.
6. Run evaluation once before inspecting individual test failures.

Do not restore the old `evaluation/ir` data or outputs as training material.
