# Responsibility Scope Management

<!--
@dependency-start
contract reference
responsibility Documents the canonical total single-owner relation for tracked paths in each repository.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared runtime projection policy
upstream design ../runtime/shared-runtime-surfaces.toml shared surface projection mechanics
upstream design ../structure/repo-structure-contract.toml separate path existence and kind contract
upstream design ../../responsibility-scope.toml machine-readable repo-local ownership manifest
downstream design ../../templates/documents/responsibility-scope.template.toml starter manifest for template-derived repositories
upstream design ../../tools/catalog.yaml structured tool ownership
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates total single ownership
downstream implementation ../../tools/agent_tools/import_responsibility.py validates local import ownership
downstream implementation ../../tools/agent_tools/task_authority.py owns protected external dependency authority
downstream implementation ../../tools/agent_tools/tool_drift.py validates scope/tool trace links
@dependency-end
-->

Repository surfaces are managed by responsibility scope, not only by file path.
The source of truth is a top-level `responsibility-scope.toml` in the repository
being checked. AgentCanon owns the validator and starter template; it does not
own the responsibility map for template-derived repositories.

## Reader Map

- Owns responsibility-scope owner classes, the total single-owner invariant,
  import boundaries, tool contracts, issue/GitHub sync, and eval evidence.
- Main path: Ownership Relation, Owner Classes, Tool Contract, Issue And GitHub
  Sync, and Eval Evidence.
- Read this before changing responsibility-scope tooling, owner labels, or
  protecting-tool evidence.
- Boundary: path existence and filesystem kind belong to
  `repo-structure-contract.toml`; projection mechanics belong to
  `shared-runtime-surfaces.toml`.

## Ownership Relation

Let `P` be the finite set returned by `git ls-files` and let `S` be the finite
set of `[[scope]]` rows. A scope owns a tracked path when at least one `paths`
pattern matches and no `exclude_paths` pattern matches. The manifest is valid
exactly when this relation is total and single-valued:

```text
for every p in P, there exists exactly one s in S such that s owns p
```

This is an ownership relation over paths that actually exist in the tracked
tree. A pattern may therefore have an empty preimage: optional, retired, or
future paths such as `.agents/**`, `agents/**`, or `examples/**` do not fail
ownership validation merely because they are absent. Required existence and
filesystem kind are separate facts and must be declared only in the structure
contract.

Each scope declares:

- `owner`: who owns the surface.
- `class`: what kind of responsibility the surface carries.
- `paths`: path patterns included in the ownership relation.
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

`tools/agent_tools/responsibility_scope.py` validates the manifest. It scans the
tracked path set once and fails when a tracked path has no owning scope or more
than one owning scope after exclusions, a scope names a missing or uncataloged
protecting tool, an issue link is stale, or an `[[import_rule]]` points at an
unknown scope. It does not require every glob to match and it does not check
required path existence or kind.

Use it before adding a new checker, hook, skill, workflow, issue family, or
tracked top-level path:

```bash
python3 tools/agent_tools/responsibility_scope.py --root .
```

`tools/agent_tools/import_responsibility.py` uses the same manifest for code
imports. It parses Python AST, flags unused imported aliases and wildcard
imports, resolves local imports to files when possible, and rejects source-scope
to target-scope crossings that are not present in `[[import_rule]]`. Because
tracked paths have exactly one owning scope, import resolution consumes the same
canonical relation instead of choosing among competing owner maps.

```bash
python3 tools/agent_tools/import_responsibility.py --root .
python3 tools/agent_tools/import_responsibility.py --root . --changed
```

`tools/agent_tools/task_authority.py` owns direct rewrite authority for vendored
or installed library implementation files. External code changes must be a
wrapper/adapter, fork/upstream patch, or manifest-backed vendor import rather
than an in-place patch to library internals.

For template or derived repositories, run the checker from the parent root. The
tool expects the parent repository to carry its own top-level
`responsibility-scope.toml`. Use
`vendor/agent-canon/templates/documents/responsibility-scope.template.toml` as
the starter when initializing that file, then specialize it until every tracked
path has exactly one owner.

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
