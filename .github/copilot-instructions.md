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
- `.github/instructions/pr-processing.instructions.md`

## Defaults

- 日本語で対応してください。
- repo 全体の正本は `documents/` と `agents/` にあります。
- 長期に残す agent ルールは `agents/` 側を更新し、このファイルは薄く保ってください。

## Skills

- Project skills are curated under `.agents/skills/`.
- If a task matches a project skill, use the skill before inventing a new local workflow.
- CLI/runtime differences are summarized in `agents/canonical/CLI_ENTRYPOINTS.md`.
- For issue, PR, and IDE tasks, follow `agents/workflows/github-copilot-workflow.md` before adding Copilot-only instructions.
- For PR triage, use `.github/instructions/pr-processing.instructions.md`; if
  custom agents are available, select `.github/agents/pr-maintainer.md`.

## Pull Requests

- Use `.github/PULL_REQUEST_TEMPLATE.md` for normal template or repo-local changes.
- Use `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` when a template PR changes `vendor/agent-canon/`.
- In the standalone AgentCanon repository, use its `.github/PULL_REQUEST_TEMPLATE.md`.
- Keep validation evidence explicit; do not mark commands complete if Copilot could not run them.
- If PR checks fail before tests with `repository ... agent-canon.git not found`,
  treat it as private submodule authentication. The repository needs
  `AGENT_CANON_REPO_TOKEN` with read-only Contents access to AgentCanon, or
  `AGENT_CANON_REPO_SSH_KEY` from a read-only deploy key, or AgentCanon must be
  made public by a human security decision.
- If PR checks fail with `AGENT_CANON_SUBMODULE_AUTH=missing`, do not change
  code to hide the failure. Record that repository secret
  `AGENT_CANON_REPO_TOKEN` or `AGENT_CANON_REPO_SSH_KEY` is missing or
  unavailable in that run context.
- If `AGENT_CANON_SUBMODULE_AUTH=token_persisted` or
  `AGENT_CANON_SUBMODULE_AUTH=ssh_persisted` appears and a later same-job step
  still fails with `could not read Username`, treat the helper persistence path
  as broken instead of changing individual validation commands.

## Validation

```bash
make ci-quick
make ci
```
