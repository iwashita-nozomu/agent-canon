# GitHub Copilot Repository Instructions
<!--
@dependency-start
@dependency-end
-->


## Read First

- `AGENTS.md`
- `agents/README.md`
- `documents/README.md`

## Defaults

- 日本語で対応してください。
- repo 全体の正本は `documents/` と `agents/` にあります。
- 長期に残す agent ルールは `agents/` 側を更新し、このファイルは薄く保ってください。

## Skills

- Project skills are curated under `.agents/skills/`.
- If a task matches a project skill, use the skill before inventing a new local workflow.
- CLI/runtime differences are summarized in `agents/canonical/CLI_ENTRYPOINTS.md`.

## Validation

```bash
make ci-quick
make ci
```
