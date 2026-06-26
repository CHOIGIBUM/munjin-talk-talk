# Generated IR Datasets

This directory is reserved for v2 generated datasets.

Expected files after generation:

```text
train_100/
  blueprint.json
  cases.json
  manifest.json

test_1000/
  blueprint.json
  cases.locked.json
  manifest.json
```

`train_100` may be inspected and used to derive alias/few-shot proposals. `test_1000` must stay locked until a one-time evaluation run is reported.
