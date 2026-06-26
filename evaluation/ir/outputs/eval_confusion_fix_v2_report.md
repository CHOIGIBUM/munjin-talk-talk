# Repeated Confusion Fix v2

## Scope

This patch addresses repeated extraction/linking confusions found in the synthetic 1000-case evaluation.

Main confusion groups:

- `객혈 -> 기침`
- `빈맥 -> 가슴 두근거림`
- `가슴 답답 -> 흉부압박감`
- `오한 -> 온몸이 떨림`
- `부정맥 -> 삼키기 곤란/빈호흡`

## Changes

- Added domain alias priority rules for:
  - cough-associated blood, blood-streaked sputum -> `객혈`
  - skipped/irregular pulse -> `부정맥`
  - fast pulse/fast heartbeat -> `빈맥`
  - blocked/stuffy/tight chest without pressure language -> `가슴 답답`
  - coldness with shaking -> `오한`
- Added extraction prompt boundary rules for:
  - not splitting `기침할 때 피` into generic cough
  - distinguishing tachycardia from palpitation
  - distinguishing arrhythmia from dysphagia/rapid breathing
  - distinguishing chest discomfort from chest pressure
  - keeping nasal-obstruction-related `답답함` under nasal obstruction, not chest discomfort
  - splitting coordinated active symptoms when both are allowed symptoms
  - preserving explicit patient anxiety as active anxiety

## Validation

Syntax checks:

- `python -m json.tool backend/serverless/src/data/domain_packs/respiratory.json`
- `python -m py_compile backend/serverless/src/extraction_prompts.py`

Spot checks from previous failure rows now prefer the intended canonical names:

- `기침할 때 피가 보여` -> `객혈`
- `기침하면 피가 비쳐` -> `객혈`
- `심장이 빠르게 뛰는 느낌이야` -> `빈맥`
- `맥이 너무 빨리 뛰어` -> `빈맥`
- `맥이 건너뛰는 느낌이야` -> `부정맥`
- `가슴이 꽉 막힌 거 같아` -> `가슴 답답`
- `추워가 몸땡이가 떨려` -> `오한`
- `몸이 춥고 떨려` -> `오한`

## Metrics

Baseline before confusion fix on synthetic 1000:

- Micro F1: `0.8229`
- Macro F1: `0.8205`
- Exact match: `0.7240`
- FPR: `0.1796`
- FNR: `0.1747`

Full synthetic 1000 after v1 confusion fix:

- Micro F1: `0.9679`
- Macro F1: `0.9684`
- Exact match: `0.9310`
- FPR: `0.0388`
- FNR: `0.0253`
- Validator pass: `0.9980`
- Error rate: `0.0020`

Final v2 patch limited validation on the first 200 synthetic cases:

- Micro F1: `0.9833`
- Macro F1: `0.9797`
- Exact match: `0.9550`
- FPR: `0.0134`
- FNR: `0.0200`
- Validator pass: `1.0000`
- Error rate: `0.0000`

Final prompt-included smoke validation on the first 50 synthetic cases:

- Micro F1: `1.0000`
- Macro F1: `1.0000`
- Exact match: `1.0000`
- FPR: `0.0000`
- FNR: `0.0000`
- Validator pass: `1.0000`
- Error rate: `0.0000`

Full synthetic 1000 after v2 confusion fix, before the follow-up cleanup patch:

- Micro F1: `0.9788`
- Macro F1: `0.9765`
- Exact match: `0.9520`
- FPR: `0.0270`
- FNR: `0.0153`
- Validator pass: `0.9980`
- Error rate: `0.0020`

IR/linker on that full v2 run:

- CandidateRecall@20: `0.9842`
- SelectedRecall@20: `0.9453`
- Linker Micro F1: `0.9552`
- Linker Macro F1: `0.9459`
- Linker Exact match: `0.9100`

Targeted recheck on the 48 failing cases after the follow-up cleanup patch:

- Micro F1: `0.9459`
- Macro F1: `0.9456`
- Exact match: `0.8333`
- FPR: `0.0789`
- FNR: `0.0278`
- Validator pass: `1.0000`
- Error rate: `0.0000`

The targeted 48-case failure count dropped from `48` to `8`.
The remaining 8 failures are mostly dataset policy issues:

- 6 cases say "배가 아프고 설사를 해" but the gold label omits abdominal pain.
- 1 case says "지난 진료 이후 구토가 있었어" but the extraction only kept chest pain.
- 1 case says "얼굴빛이 창백해 보여" but no active pallor span was produced.

IR/linker on the same 200-case v2 run:

- CandidateRecall@20: `0.9742`
- SelectedRecall@20: `0.9458`
- Linker Micro F1: `0.9561`
- Linker Macro F1: `0.9468`
- Linker Exact match: `0.9000`

## Remaining Notes

Some remaining failures appear to be data-label policy inconsistencies rather than model/linker defects:

- `심장이 빨리 뛰는 느낌` is labeled as `빈맥` in some cases and `가슴 두근거림` in another.
- `배가 아프고 설사를 해` is sometimes labeled only as `설사`, although the utterance contains abdominal pain.
- Follow-up text such as `사레가 잘 들어` can be interpreted as improved/resolved, but some gold labels keep `사래걸림` active.

These should be resolved in the dataset policy before using the synthetic 1000 as a strict final benchmark.
