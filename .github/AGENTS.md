# GitHub Agent Entry Point
<!--
@dependency-start
responsibility Documents GitHub Agent Entry Point for this repository.
upstream design ../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
upstream design ../documents/github-copilot-configuration.md Copilot configuration catalog
@dependency-end
-->


GitHub 側の薄い入口です。

- shared instructions: `/AGENTS.md`
- human canonical hub: `/agents/README.md`
- copilot custom instructions: `/.github/copilot-instructions.md`
- copilot PR processing instructions: `/.github/instructions/pr-processing.instructions.md`
- copilot PR maintainer custom agent: `/.github/agents/pr-maintainer.md`
- copilot configuration catalog: `/vendor/agent-canon/documents/github-copilot-configuration.md`
  in template roots; `/documents/github-copilot-configuration.md` in standalone
  AgentCanon
- curated project skills: `/.agents/skills/`
- default PR checklist: `/.github/PULL_REQUEST_TEMPLATE.md`
- AgentCanon-in-template PR checklist: `/.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
- Plan mode: use `/plan` or an explicit written plan before non-trivial
  GitHub Actions, Copilot settings, PR-template, AgentCanon sync, or multi-file
  runtime-surface changes.
