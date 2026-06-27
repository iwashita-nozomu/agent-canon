# Responsibility Scope Management

<!--
@dependency-start
contract reference
responsibility Documents machine-readable responsibility scope management for each repository.
upstream design SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
upstream design shared-runtime-surfaces.toml shared surface manifest
upstream design ../responsibility-scope.toml machine-readable repo-local scope manifest
downstream design templates/responsibility-scope.template.toml starter manifest for template-derived repositories
upstream design ../tools/catalog.yaml structured tool ownership
downstream implementation ../tools/agent_tools/responsibility_scope.py validates scope coverage
downstream implementation ../tools/agent_tools/import_responsibility.py validates local import ownership
downstream implementation ../.codex/hooks/library_implementation_guard.py blocks protected external dependency rewrites
downstream implementation ../.codex/hooks/helper_first_guard.py blocks helper-first implementation drift
downstream implementation ../tools/agent_tools/tool_drift.py validates scope/tool trace links
@dependency-end
-->

Repository surfaces are managed by responsibility scope, not only by file path.
The source of truth is a top-level `responsibility-scope.toml` in the repository
being checked. AgentCanon owns the validator and starter template; it does not
own the responsibility map for template-derived repositories.

## Reader Map

- Owns responsibility-scope owner classes, tool contracts, issue/GitHub sync,
  and eval evidence expectations.
- Main path: Owner Classes, Tool Contract, Issue And GitHub Sync, and Eval
  Evidence.
- Read this before changing responsibility-scope tooling, owner labels, or
  protecting-tool evidence.
- Boundary: it defines scope-management contracts, not task-specific ownership
  decisions for a single run.

Each scope declares:

- `owner`: who owns the surface.
- `class`: what kind of responsibility the surface carries.
- `paths`: path patterns covered by the scope.
- `exclude_paths`: optional path patterns removed from a broad `paths` claim.
  Use this when a cross-cutting surface inside a broad directory has a
  different owning responsibility.
- `protecting_tools`: checkers or workflow tools that keep the scope valid.
- `issues`: durable local issues that currently drive or explain the scope.

Each `[[import_rule]]` declares which local Python scope imports are allowed:

- `source`: the responsibility scope of the importing file.
- `targets`: responsibility scopes that the source scope may import when the
  import resolves to a local repository file.

## Owner Classes

- `agent-canon`: shared runtime, policy, tooling, memory, eval, and issue state
  maintained in the AgentCanon repository.
- `template`: template-local active contracts and parent-repo integration files.
- `derived-project`: project-owned implementation, experiments, reports, and
  durable project state.
- `github`: GitHub Actions, PR templates, GitHub automation, and GitHub
  Issue mirror behavior.
- `external-vendor`: third-party skills or agent components vendored into
  AgentCanon. GitHub-sourced external repositories stay below
  `vendor/<asset-class>/<github-owner>/<import-id>/` and are exposed through
  adapters or manifests rather than copied into canonical runtime paths.

## Tool Contract

`tools/agent_tools/responsibility_scope.py` validates the manifest. It fails
when a required top-level surface has no scope, a tracked file is claimed by
multiple scopes after `exclude_paths` are applied, a scope names a missing tool,
a tool is not present in `tools/catalog.yaml`, an issue link is stale, or an
`[[import_rule]]` points at an unknown scope.

Use it before adding a new checker, hook, skill, workflow, or issue family:

```bash
python3 tools/agent_tools/responsibility_scope.py --root .
```

`tools/agent_tools/import_responsibility.py` uses the same manifest for code
imports. It parses Python AST, flags unused imported aliases and wildcard
imports, resolves local imports to files when possible, and rejects source-scope
to target-scope crossings that are not present in `[[import_rule]]`. Scope
resolution applies `exclude_paths` before choosing the most specific matching
scope, so an evidence or state file inside a broad runtime/tooling directory can
carry its own import boundary.

```bash
python3 tools/agent_tools/import_responsibility.py --root .
python3 tools/agent_tools/import_responsibility.py --root . --changed
```

Edit-time hooks use the same ownership model for two common failure modes:

- `.codex/hooks/library_implementation_guard.py` blocks direct rewrites of
  vendored or installed library implementation files. External code changes
  must be a wrapper / adapter, fork / upstream patch, or manifest-backed vendor
  import rather than an in-place patch to library internals.
- `.codex/hooks/helper_first_guard.py` blocks helper-like function additions
  that do not carry ownership evidence such as a test, issue, docs, or
  responsibility-scope update. Its JSONL records include role, candidate rule,
  judgment rule, incoming count, and specialization so prompt and skill evals
  can identify where agents started from helpers instead of an owning contract.

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
the mounted `.agent-canon/log-archive/` archive. The source tree must not
contain an `agents/evals/results/` result surface. They are validated by:

```bash
python3 tools/agent_tools/eval_accumulation_check.py --root .
```

This gate checks structure, ignored-file status, JSONL readability, and unique
run identifiers. It does not delete or compact old results; retention is a
separate explicit maintenance task.
