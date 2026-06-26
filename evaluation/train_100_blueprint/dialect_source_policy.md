# Train 100 Dialect Source Policy

This document clarifies what the `kangwon` label means in `train_100`.

## Finding

`train_100` was useful for rebuilding the respiratory domain pack, aliases, few-shots, and runtime RAG candidate ranking. However, its 50 Kangwon rows were not originally separated by dialect evidence source.

After checking the runtime dialect RAG pack:

- `backend/serverless/src/data/dialect_packs/dialect_kangwon.csv`
- `backend/serverless/src/data/dialect_packs/dialect_kangwon.json`

only a small part of `train_100` is directly anchored in the current dialect pack. Most Kangwon rows are better described as medical colloquial or light dialect-flavored Korean.

## Current Train 100 Source-Layer Counts

| Layer | Count | Meaning |
| --- | ---: | --- |
| `none` | 50 | Standard Korean rows |
| `rag_pack_anchored` | 1 | Contains a useful expression directly grounded in the current dialect pack |
| `train_validated_medical_colloquial` | 17 | Medical colloquial forms validated by train_100, not necessarily present in the dialect pack |
| `light_dialect_flavor` | 32 | Mostly standard symptom speech with light local cadence or endings |

## Layer Definitions

### `rag_pack_anchored`

Directly grounded in the current Gangwon dialect pack. In the accepted train set, this is currently limited.

Example:

- `몸땡이` -> `몸통`

### `train_validated_medical_colloquial`

Medical-intake colloquial forms that worked in `train_100` and generated runtime few-shot examples. These are not claimed as current dialect-pack terms.

Examples:

- `가심`
- `맥혀`
- `코물`
- `아푸고`, `아퍼`
- `아녀`, `않어`
- `하니`, `영`

### `light_dialect_flavor`

Rows that are labeled Kangwon because the style is slightly local or colloquial, but they do not contain a reliable current dialect-pack anchor or a distinctive medical colloquial feature.

## Research Interpretation

Do not report `train_100` as if all Kangwon rows are dialect-RAG-grounded. The correct statement is:

> `train_100` contains 50 Kangwon-labeled rows, mostly medical colloquial or light dialect-flavored utterances. Actual dialect-pack-grounded coverage is limited and is now tracked separately by `dialect_source_layer`.

The separate `test_1000` design intentionally adds more `rag_pack_anchored` rows to measure dialect RAG behavior directly.
