# Responsibility Scope Management

<!--
@dependency-start
responsibility Documents machine-readable responsibility scope management for each repository.
upstream design SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
upstream design shared-runtime-surfaces.toml shared surface manifest
upstream design ../responsibility-scope.toml machine-readable repo-local scope manifest
downstream design templates/responsibility-scope.template.toml starter manifest for template-derived repositories
upstream design ../tools/catalog.yaml structured tool ownership
downstream implementation ../tools/agent_tools/responsibility_scope.py validates scope coverage
downstream implementation ../tools/agent_tools/tool_drift.py validates scope/tool trace links
@dependency-end
-->

Repository surfaces are managed by responsibility scope, not only by file path.
The source of truth is a top-level `responsibility-scope.toml` in the repository
being checked. AgentCanon owns the validator and starter template; it does not
own the responsibility map for template-derived repositories.

Each scope declares:

- `owner`: who owns the surface.
- `class`: what kind of responsibility the surface carries.
- `paths`: path patterns covered by the scope.
- `protecting_tools`: checkers or workflow tools that keep the scope valid.
- `issues`: durable local issues that currently drive or explain the scope.

## Owner Classes

- `agent-canon`: shared runtime, policy, tooling, memory, eval, and issue state
  maintained in the AgentCanon repository.
- `template`: template-local active contracts and parent-repo integration files.
- `derived-project`: project-owned implementation, experiments, reports, and
  durable project state.
- `github`: GitHub Actions, PR templates, Copilot configuration, and GitHub
  Issue mirror behavior.
- `external-vendor`: third-party skills or agent components vendored into
  AgentCanon. GitHub-sourced external repositories stay below
  `vendor/<asset-class>/<github-owner>/<import-id>/` and are exposed through
  adapters or manifests rather than copied into canonical runtime paths.

## Tool Contract

`tools/agent_tools/responsibility_scope.py` validates the manifest. It fails
when a required top-level surface has no scope, a scope names a missing tool, a
tool is not present in `tools/catalog.yaml`, or an issue link is stale.

Use it before adding a new checker, hook, skill, workflow, or issue family:

```bash
python3 tools/agent_tools/responsibility_scope.py --root .
```

For template or derived repositories, run it from the parent root. The tool
expects the parent repository to carry its own top-level
`responsibility-scope.toml`. Use
`vendor/agent-canon/documents/templates/responsibility-scope.template.toml` as
the starter when initializing that file.

## Issue And GitHub Sync

Local `issues/open|closed/` files remain the durable source of truth because
they carry dependency headers, edit scope, and reviewable history. GitHub
Issues are the visible mirror for triage and external automation.

`tools/agent_tools/issue_sync.py` validates the local files offline and can
plan missing GitHub mirrors. Creating or updating GitHub Issues is an explicit
operator action; CI should use offline validation by default.

## Eval Evidence

Eval and hook results are AgentCanon-owned evidence. They live under
`agents/evals/results/` and are validated by:

```bash
python3 tools/agent_tools/eval_accumulation_check.py --root .
```

This gate checks structure, ignored-file status, JSONL readability, and unique
run identifiers. It does not delete or compact old results; retention is a
separate explicit maintenance task.
