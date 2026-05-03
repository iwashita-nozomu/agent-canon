# static-validation
<!--
@dependency-start
responsibility Documents static-validation for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

変更内容に応じて最小限かつ十分な quality gate を選びます。

## Use When

- 何を検証すべきか決めたい
- docs / code / environment 変更の確認をそろえたい

## Standard Checks

- `make ci-quick`
- `make ci`
- `make docs-check`
- `python3 tools/agent_tools/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports`

## Numeric Literal Gate

- Python / C++ implementation changes must run `check_hardcoded_numbers.py` before closeout.
- `HARDCODED_NUMBERS=fail` is not a style-only warning. Fix it by naming the value, moving it to typed configuration / API input, or adding a local `hardcoded-number-ok` reason when the literal is clearer in the formula.
- Test fixture numbers are excluded from the default changed-source gate, but nontrivial repeated test parameters should still be named in the test file.

## Boundary

- `static-check` は Codex skill 名互換の入口です。
- どの gate を組み合わせるかの正本はこの文書です。
