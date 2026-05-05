# GitHub Copilot Workflow
<!--
@dependency-start
responsibility Documents the GitHub Copilot workflow for repository and AgentCanon tasks.
upstream design ../canonical/CLI_ENTRYPOINTS.md defines runtime entrypoints
upstream design agent-canon-pr-workflow.md defines shared canon PR discipline
downstream design ../../.github/copilot-instructions.md consumes Copilot workflow
downstream design ../workflows/README.md indexes workflow routing
@dependency-end
-->

This workflow keeps GitHub Copilot aligned with the same repository contract as
Codex while respecting that Copilot often starts from an issue, PR, or IDE
context rather than a prepared local run bundle.

## Entry Packet

1. Read `.github/copilot-instructions.md`.
1. Read `AGENTS.md`.
1. Read `agents/README.md`.
1. Read `documents/README.md`.
1. If the task touches shared AgentCanon surfaces, read
   `agents/workflows/agent-canon-pr-workflow.md`.
1. If the task touches GitHub Actions or PR templates, read this workflow and
   `.github/PULL_REQUEST_TEMPLATE.md` or
   `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` as applicable.

## Operating Rules

- Keep `.github/copilot-instructions.md` as a thin runtime entrypoint.
- Do not create Copilot-only policy that conflicts with `AGENTS.md` or
  AgentCanon workflows.
- Prefer existing tools and workflow docs before adding new GitHub-only helper
  scripts.
- Treat root shared surfaces as views into `vendor/agent-canon/`; edit the
  AgentCanon source when the change is shared.
- When Copilot cannot run a local command, leave a PR checklist item with the
  exact command and the missing environment reason instead of marking it done.

## GitHub Actions Changes

For `.github/workflows/*.yml` changes:

- Checkout must include `submodules: true` when the job needs AgentCanon-backed
  root surfaces.
- Workflows should declare minimal `permissions`.
- Long-running validation workflows should use `concurrency` to avoid stale
  duplicate runs unless the workflow is intentionally fan-out oriented.
- Job names should describe the gate they enforce, not only the tool they call.
- Validation must include the repository command that the workflow wraps, such
  as `make ci`, `make agent-canon-pr-check`, or Docker pack checks.

## PR Checklist Use

- Template-local PRs use `.github/PULL_REQUEST_TEMPLATE.md`.
- Template PRs that edit `vendor/agent-canon/` also use
  `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`.
- Standalone AgentCanon PRs use AgentCanon's own
  `.github/PULL_REQUEST_TEMPLATE.md`.
- If a PR changes Copilot instructions, include the expected read packet and
  the validation command in the PR body.

## Closeout

Before Copilot-authored changes are accepted:

1. Confirm the PR checklist maps every requested requirement to evidence.
1. Confirm shared surfaces are synchronized with
   `bash tools/sync_agent_canon.sh check`.
1. Confirm dependency review and task-relevant validation pass.
1. Confirm AgentCanon changes have an upstream path before template pins are
   updated.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
