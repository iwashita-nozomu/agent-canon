# GitHub Copilot Repository Instructions
<!--
@dependency-start
responsibility Documents GitHub Copilot Repository Instructions for this repository.
upstream design ../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
upstream design ../agents/workflows/github-copilot-workflow.md Copilot runtime workflow
@dependency-end
-->


## Read First

- `AGENTS.md`
- `agents/README.md`
- `documents/README.md`
- `agents/workflows/github-copilot-workflow.md`

## Defaults

- 日本語で対応してください。
- repo 全体の正本は `documents/` と `agents/` にあります。
- 長期に残す agent ルールは `agents/` 側を更新し、このファイルは薄く保ってください。

## Skills

- Project skills are curated under `.agents/skills/`.
- If a task matches a project skill, use the skill before inventing a new local workflow.
- CLI/runtime differences are summarized in `agents/canonical/CLI_ENTRYPOINTS.md`.
- For issue, PR, and IDE tasks, follow `agents/workflows/github-copilot-workflow.md` before adding Copilot-only instructions.

## Pull Requests

- Use `.github/PULL_REQUEST_TEMPLATE.md` for normal template or repo-local changes.
- Use `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` when a template PR changes `vendor/agent-canon/`.
- In the standalone AgentCanon repository, use its `.github/PULL_REQUEST_TEMPLATE.md`.
- Keep validation evidence explicit; do not mark commands complete if Copilot could not run them.

## Validation

```bash
make ci-quick
make ci
```
