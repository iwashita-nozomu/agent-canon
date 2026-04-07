# agent-orchestration

## Purpose

task を workflow family に分類し、handoff、review、runtime entrypoint を一貫した形にそろえます。

## Use When

- どの workflow family を使うか決めたい
- run bundle や review artifact の要否を決めたい
- Codex / Claude / Copilot 間で共通ルールを保ちたい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`

## Outputs

- chosen workflow family
- 必要な role / specialist
- review と handoff の最小構成
- repo-editing task なら、requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> implementation の順序
