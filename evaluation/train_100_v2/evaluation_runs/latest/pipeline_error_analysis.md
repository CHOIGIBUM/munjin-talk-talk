# Pipeline Error Analysis

Dataset: `evaluation/train_100_v2/train_100_v2.jsonl`

This is not a held-out score. It is a train-set pipeline inspection run used to
separate candidate-search quality from actual Bedrock extraction and linking.

## Final Summary

- Completed rows: 100/100
- Schema/runtime failures: 0
- Source quote grounding rate: 1.0
- RAG context node seen rate: 1.0
- Pipeline symptom precision: 1.0000
- Pipeline symptom recall: 0.9279
- Pipeline symptom F1: 0.9626
- Negative false-positive rate among rows with negative symptoms: 0.0000

Previous pipeline inspection before the runtime fixes was:

- Precision: 0.9091
- Recall: 0.7207
- F1: 0.8040
- Negative false-positive rate: 0.1364

## What Changed

The main bottleneck was not candidate availability. Track A combined IR already
had recall@5 = 1.0, while Track C lost symptoms after Bedrock extraction and
linking. The implemented fixes target that gap:

1. `slot_ref` is now trusted before broad source-text aliases when the slot has
   its own evidence in the span.
2. If the LLM `slot_ref` is wrong but the span name directly matches another
   canonical symptom, the direct symptom name can override the wrong slot.
3. Broad source quotes are narrowed with domain quote patterns before IR query
   construction.
4. Active `context` spans can be rescued when their name/slot maps to an
   ontology symptom.
5. Local nasal obstruction is guarded so "코가 막혀 숨쉬기 힘듦" maps to
   `코막힘`, not `호흡곤란`.
6. Agenda-only anxiety and nonspecific GI overreads are filtered before IR.
7. A limited co-occurring symptom rescue adds a second active symptom only for
   high-signal patterns such as `호흡곤란 + 가슴 답답` or `다리 붓기`.
8. Duplicate matched slots are collapsed to one output per canonical slot.

## Final Remaining Mismatches

The final run has 8 mismatch rows, all false negatives. There are no false
positives.

All 8 remaining misses are `progress_improved/status=없음` spans:

- `train_v2_055`: 호흡곤란이 조금 나아졌지만 여전히 힘들 때가 있음
- `train_v2_056`: 가슴 답답함이 덜해짐
- `train_v2_064`: 열이 나아진 것 같음
- `train_v2_065`: 오한이 줄어든 것 같음
- `train_v2_066`: 근육통이 조금 나아짐
- `train_v2_068`: 기운없음이 조금 나아짐
- `train_v2_070`: 피로감은 덜하지만 근육통은 현재 남음
- `train_v2_076`: 목소리 변화가 조금 나아짐

Current product policy intentionally excludes `progress_improved` and
`symptom_absent` from active symptom cards and IR `matched_slots`. These items
are preserved as follow-up context/clinical clues, not "오늘 말한 불편함".
Therefore the remaining recall loss is a scoring-policy mismatch rather than a
candidate-search or IR-linking failure.

## Track-Level Interpretation

- Track A remains an offline candidate-search test. It does not call Bedrock.
- Track B confirms the Gangwon dialect RAG layer is invoked and anchored rows
  are retrieved.
- Track C is the actual end-to-end Bedrock pipeline test with S3/DynamoDB
  persistence monkeypatched.

## Next Reporting Rule

Do not report this as final held-out performance. The first publishable model
score must be run on locked `test_1000_v2` after it is generated and frozen.

For the held-out report, split metrics into:

- active symptom F1: `matched_slots` only
- follow-up context coverage: `progress_improved` and `symptom_absent`
- negative symptom false-positive rate
