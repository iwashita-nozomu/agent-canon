# GitHub Copilot Workflow
<!--
@dependency-start
responsibility Documents the GitHub Copilot workflow for repository and AgentCanon tasks.
upstream design ../canonical/CLI_ENTRYPOINTS.md defines runtime entrypoints
upstream design agent-canon-pr-workflow.md defines shared canon PR discipline
upstream design ../../documents/github-copilot-configuration.md Copilot configuration catalog
downstream design ../../.github/copilot-instructions.md consumes Copilot workflow
downstream design ../workflows/README.md indexes workflow routing
@dependency-end
-->

This workflow keeps GitHub Copilot aligned with the same repository contract as
Codex while respecting that Copilot often starts from an issue, PR, or IDE
context rather than a prepared local run bundle.

## Entry Packet

1. Read `.github/copilot-instructions.md`.
1. Read `.github/instructions/pr-processing.instructions.md` when available.
1. Read `AGENTS.md`.
1. Read `documents/github-copilot-configuration.md`.
1. Read `agents/README.md`.
1. Read `documents/README.md`.
1. If the task touches shared AgentCanon surfaces, read
   `agents/workflows/agent-canon-pr-workflow.md`.
1. If the task touches GitHub Actions or PR templates, read this workflow and
   `.github/PULL_REQUEST_TEMPLATE.md` or
   `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` as applicable.
1. If GitHub custom agents are available and the task is PR triage or PR
   maintenance, use `.github/agents/pr-maintainer.md`.

## Copilot Customization Surfaces

- `.github/copilot-instructions.md` is the thin repository-wide entrypoint.
- `.github/instructions/pr-processing.instructions.md` is the path-wide PR
  processing instruction file used by Copilot cloud agent and Copilot code
  review.
- `.github/agents/pr-maintainer.md` is the optional custom agent profile for
  PR maintenance and check-failure triage.
- `documents/github-copilot-configuration.md` is the catalog for GitHub
  Copilot settings, custom agent frontmatter, MCP placement, Copilot setup
  workflows, and PR-template routing.
- Keep these surfaces synchronized through AgentCanon. Do not add one-off
  Copilot rules in derived repos unless the rule is truly repo-local.

## Plan Mode And Multi-Agent Routing

- Use Plan mode before non-trivial GitHub Actions, Copilot settings, PR
  templates, AgentCanon sync, or multi-file runtime-surface changes.
- Codex uses `/plan` when available. If a GitHub Copilot surface lacks an
  explicit Plan mode command, write the plan in the issue, PR body, or PR
  comment before editing.
- Use custom agents or subagents for bounded sidecar work such as PR triage,
  existing-surface survey, or adversarial test design. Keep implementation
  ownership clear and do not let a triage agent become the closeout authority.

## Operating Rules

- Keep `.github/copilot-instructions.md` as a thin runtime entrypoint.
- Do not create Copilot-only policy that conflicts with `AGENTS.md` or
  AgentCanon workflows.
- Treat Copilot as a contributor surface, not as the closeout authority. Codex
  closeout gates, full-repo dependency review, static analysis, AgentCanon pin
  evidence, and PR checklist evidence still need to be produced by the repo
  workflow before a Copilot-authored change is accepted.
- Prefer existing tools and workflow docs before adding new GitHub-only helper
  scripts.
- Treat root shared surfaces as views into `vendor/agent-canon/`; edit the
  AgentCanon source when the change is shared.
- When Copilot cannot run a local command, leave a PR checklist item with the
  exact command and the missing environment reason instead of marking it done.
- When Copilot changes AgentCanon-owned text, require the same submodule-era
  sequence as Codex: source change in AgentCanon, `make agent-canon-pr-check`,
  template submodule pin update, and root shared-surface drift check.

## GitHub Actions Changes

For `.github/workflows/*.yml` changes:

- Checkout must fetch the root repository first with `submodules: false` and
  `persist-credentials: false`.
- Jobs that need AgentCanon-backed root surfaces must then run
  `bash .github/scripts/checkout_agent_canon_submodule.sh` with
  `AGENT_CANON_REPO_TOKEN: ${{ secrets.AGENT_CANON_REPO_TOKEN }}`.
- Do not use `actions/checkout` automatic submodule checkout for private
  AgentCanon repos. It fails before the repository helper can print an
  actionable remediation.
- Workflows should declare minimal `permissions`.
- Long-running validation workflows should use `concurrency` to avoid stale
  duplicate runs unless the workflow is intentionally fan-out oriented.
- Job names should describe the gate they enforce, not only the tool they call.
- Validation must include the repository command that the workflow wraps, such
  as `make ci`, `make agent-canon-pr-check`, or Docker pack checks.

## Private AgentCanon Submodule Failures

If GitHub Actions or Copilot PR processing shows `Repository not found` while
cloning `vendor/agent-canon`, diagnose authentication before changing code.
`GITHUB_TOKEN` is scoped to the current repository, so a private AgentCanon
submodule needs one of these human-controlled fixes:

- Add repository secret `AGENT_CANON_REPO_TOKEN` with read-only Contents access
  to `iwashita-nozomu/agent-canon`.
- Add repository secret `AGENT_CANON_REPO_SSH_KEY` containing the private half
  of a read-only deploy key whose public half is installed on
  `iwashita-nozomu/agent-canon`.
- Make AgentCanon public only after a human security review decides that the
  shared runtime can be public.
- Replace the PAT with a GitHub App token only after the workflow documents the
  app permissions and installation scope.

Copilot must not rewrite `.gitmodules`, remove the submodule, vendor a copied
snapshot, or mark the PR as code-broken when the only failure is missing
private-submodule credentials.

Current GitHub Actions behavior to account for:

- Workflow secrets are only available when the workflow explicitly passes them
  to a step.
- Pull requests from fork-like or untrusted contexts may not receive repository
  secrets. In that case, record the blocker and request a trusted maintainer
  rerun after reviewing the workflow diff.
- If `checkout_agent_canon_submodule.sh` prints
  `AGENT_CANON_SUBMODULE_AUTH=missing`, the next action is to configure
  `AGENT_CANON_REPO_TOKEN`, `AGENT_CANON_REPO_SSH_KEY`, or an equivalent GitHub
  App token, not to change the implementation under review.
- If `checkout_agent_canon_submodule.sh` prints
  `AGENT_CANON_SUBMODULE_AUTH=token_persisted` or
  `AGENT_CANON_SUBMODULE_AUTH=ssh_persisted`, the credential was accepted and
  the job now carries AgentCanon-specific auth for later `make ci`,
  `make fresh-clone-check`, and `make agent-canon-pr-check` steps. A later
  `could not read Username` failure in the same job means this persistence path
  regressed and should be fixed in the helper, not worked around in each
  workflow command.

## PR Error Triage

Use this order when Copilot reports a PR processing error:

1. Check whether the failure happened before dependency installation or test
   execution. If yes, inspect checkout, token, workflow syntax, or runner setup
   first.
1. Search the failed log for `AGENT_CANON_SUBMODULE_AUTH=missing`,
   `AGENT_CANON_SUBMODULE_AUTH=denied`,
   `AGENT_CANON_SUBMODULE_AUTH=ssh_denied`,
   `repository ... agent-canon.git not found`, or `could not read Username`.
1. If one of those strings appears, classify the PR as blocked on private
   AgentCanon access and leave the code diff unchanged unless there is another
   independent finding.
1. If tests or linters actually ran and failed, treat those as code or docs
   findings and fix them through the normal workflow.
1. Record the classification in the PR body or comment with the exact command,
   the failing job name, and whether the blocker is missing secret, denied
   secret, fork/untrusted context, workflow syntax, or real validation failure.

## PR Checklist Use

- Template-local PRs use `.github/PULL_REQUEST_TEMPLATE.md`.
- Template PRs that edit `vendor/agent-canon/` also use
  `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`.
- Standalone AgentCanon PRs use AgentCanon's own
  `.github/PULL_REQUEST_TEMPLATE.md`.
- If a PR changes Copilot instructions, include the expected read packet and
  the validation command in the PR body.
- If a PR changes Copilot settings, custom agents, MCP, setup workflows, or PR
  templates, include `documents/github-copilot-configuration.md`, Plan Mode
  Evidence, and Copilot Configuration Impact in the PR body.

## Closeout

Before Copilot-authored changes are accepted:

1. Confirm the PR checklist maps every requested requirement to evidence.
1. Confirm shared surfaces are synchronized with
   `bash tools/sync_agent_canon.sh check`.
1. Confirm full-repo dependency review and task-relevant validation pass, not
   just the checks Copilot could run inside the editor.
1. Confirm AgentCanon changes have an upstream path and recorded GitHub SHA
   before template pins are updated.
1. Confirm any unrun command is explicitly blocked by environment, not omitted
   because it was outside Copilot's runtime.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
