# GitHub Agent Entry Point
<!--
@dependency-start
contract reference
responsibility Documents GitHub Agent Entry Point for this repository.
upstream design ../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
@dependency-end
-->


GitHub 側の薄い入口です。

Codex loads this file only as a `.github/` subtree overlay after the root
`AGENTS.md` chain. Keep it limited to GitHub Actions, PR templates, issue
templates, and GitHub-facing automation. Repository-wide runtime, skill,
structure, validation, or closeout rules belong in the root entrypoint or the
owner surface it names, not here.

- shared instructions: `/AGENTS.md`
- human canonical hub: `/agents/README.md`
- curated project skills: `/.agents/skills/`
- default PR checklist: `/.github/PULL_REQUEST_TEMPLATE.md`
- AgentCanon-in-template PR checklist: `/.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
- Plan mode: use `/plan` or an explicit written plan before non-trivial changes
  under `.github/`, including GitHub Actions, PR templates, issue templates, and
  GitHub-facing automation.
