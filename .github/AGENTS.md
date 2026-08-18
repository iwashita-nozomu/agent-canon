# GitHub Agent Entry Point
<!--
@dependency-start
contract reference
responsibility Documents GitHub Agent Entry Point for this repository.
upstream design ../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
upstream design ../templates/documents/github/README.md canonical GitHub template source and projection map
@dependency-end
-->


GitHub 側の薄い入口です。

Codex loads this file only when the active project-root/current-directory
instruction chain enters `.github/`. It is then a subtree overlay after broader
global and root repository guidance. In this directory Codex checks
`.github/AGENTS.override.md`, then `.github/AGENTS.md`, then fallback names
listed in `project_doc_fallback_filenames`; the first non-empty match is the
only `.github/` instruction file included.

Keep this overlay limited to GitHub Actions, PR templates, issue templates, and
GitHub-facing automation. Repository-wide runtime, skill, structure,
validation, or closeout rules belong in the root entrypoint or the owner
surface it names, not here.

- shared instructions: `AGENTS.md` in standalone AgentCanon or
  `vendor/agent-canon/AGENTS.md` in a derived parent
- human canonical hub: `agents/README.md` in standalone AgentCanon or
  `vendor/agent-canon/agents/README.md` in a derived parent
- curated project skills: `.agents/skills/` in standalone AgentCanon or
  `vendor/agent-canon/.agents/skills/` in a derived parent
- canonical GitHub template source: `templates/documents/github/issue/` and
  `templates/documents/github/pull-request/` in standalone AgentCanon, or
  `vendor/agent-canon/templates/documents/github/issue/` and
  `vendor/agent-canon/templates/documents/github/pull-request/` in a derived parent
- standalone AgentCanon PR checklist: `/.github/PULL_REQUEST_TEMPLATE.md`
- generated template / derived repo AgentCanon PR checklist:
  `/.github/PULL_REQUEST_TEMPLATE/agent_canon.md`; edit the canonical source above.
- The standalone checklist is an AgentCanon-only `standalone_only` surface; it is not
  projected into a parent template root and is not a second owner of the generated
  template-side checklist.
- Plan mode: use `/plan` or an explicit written plan before non-trivial changes
  under `.github/`, including GitHub Actions, PR templates, issue templates, and
  GitHub-facing automation.
