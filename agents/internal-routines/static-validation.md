# static-validation
<!--
@dependency-start
contract agent-runtime
responsibility Documents static-validation for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

変更内容、risk、owner surface に応じて必要な quality gate を選びます。

## Use When

- 何を検証すべきか決めたい
- docs / code / environment 変更の確認をそろえたい

## Standard Checks

- `make ci-quick`
- `make ci`
- `tools/bin/agent-canon docs check`
- `python3 tools/agent_tools/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports`
- `python3 tools/agent_tools/check_convention_compliance.py`

## Numeric Literal Gate

- Python / C++ implementation changes must run `check_hardcoded_numbers.py` before closeout.
- `HARDCODED_NUMBERS=fail` is not a style-only warning. Fix it by naming the value, moving it to typed configuration / API input, or adding a local `hardcoded-number-ok` reason when the literal is clearer in the formula.
- Test fixture numbers are excluded from the default changed-source gate, but nontrivial repeated test parameters should still be named in the test file.

## Convention Compliance Gate

- Use `check_convention_compliance.py` for workflow prohibition wiring, convention source inventory, skill-routing hooks, and convention tool-gate wiring.
- Do not duplicate that detailed checklist inside each skill prompt. Prompts should call the tool and keep task-specific routing guidance only.

## Boundary

- `static-check` は Codex skill 名互換の入口です。
- どの gate を組み合わせるかの正本はこの文書です。
