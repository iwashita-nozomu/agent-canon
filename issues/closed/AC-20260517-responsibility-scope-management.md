# Responsibility Scope Management Issue

<!--
@dependency-start
contract issue
responsibility Records the finding that AgentCanon lacks a machine-readable responsibility scope map.
upstream design ../../documents/SHARED_RUNTIME_SURFACES.md defines shared runtime surface ownership.
upstream design ../../documents/shared-runtime-surfaces.toml defines shared surface classes.
upstream design ../../tools/catalog.yaml defines tool ownership.
downstream design ../../responsibility-scope.toml defines repo-local scope ownership.
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates scope ownership.
@dependency-end
-->

issue_id: AC-20260517-responsibility-scope-management
status: resolved
source: user
severity: S1
evidence: User feedback on 2026-05-17: responsibility boundaries and tool responses remain weak and need a management tool.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/243
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/312
affected_surfaces: documents/SHARED_RUNTIME_SURFACES.md, documents/shared-runtime-surfaces.toml, responsibility-scope.toml, tools/catalog.yaml, tools/README.md, documents/tools/README.md, .codex/hooks.json, .codex/hooks/library_implementation_guard.py, .codex/hooks/helper_first_guard.py, ROOT_AGENTS.md, agents/workflows/agent-canon-pr-workflow.md
edit_scope: responsibility-scope.toml, documents/templates/responsibility-scope.template.toml, documents/responsibility-scope-management.md, documents/coding-conventions-python.md, tools/agent_tools/responsibility_scope.py, tools/agent_tools/import_responsibility.py, .codex/hooks/library_implementation_guard.py, .codex/hooks/helper_first_guard.py, tests/agent_tools/test_responsibility_scope.py, tests/agent_tools/test_import_responsibility.py, tests/agent_tools/test_codex_hooks.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, tools/ci/run_all_checks.sh, agents/workflows/implementation-waterfall-workflow.md, agents/skills/codex-task-workflow.md
required_action: Add a machine-readable responsibility scope manifest and checker so tools, issues, evals, memory, GitHub surfaces, shared runtime paths, local Python import boundaries, external library boundaries and implementations, and helper-first implementation drift have explicit owners and gates.
close_condition: Checkers validate required top-level responsibility scopes, owner classes, matching tool paths, issue links, import rules, unused imports, wildcard imports, local scope import crossings, direct library implementation rewrites, external-library boundary decisions, and helper-like function additions without ownership evidence.

## Finding

AgentCanon has a shared-runtime surface manifest and a tool catalog, but there
is no single machine-readable map that says which responsibility owns issues,
evals, memory, tool gates, GitHub surfaces, and repo-facing docs together.
That gap makes tool routing reactive instead of planned.

## Required Fix

Introduce a responsibility scope manifest and checker. The manifest should
classify each durable operational surface by owner class and name the tool or
gate that protects it.

Extend the same manifest to code imports. `[[import_rule]]` entries should make
source-scope to target-scope local imports explicit, and an AST checker should
catch unused aliases and wildcard imports before agents spend tokens on changes
that style or ownership gates will reject.

Extend the edit-time hooks to stop two recurring responsibility failures:
directly patching vendored / installed library internals, and starting an
implementation by adding helper-like functions before an owning object, module
contract, issue, docs, test, or responsibility-scope evidence exists. Both
hooks must emit structured JSONL so prompt and skill evals can learn from the
rejected edit pattern.

## Additional Evidence: External Library Boundary

On 2026-05-18, a task to repair a project notebook's PDIPM usage triggered an
agent plan to change the upstream `jax_util` library API before first reading
and applying the existing public API. The user corrected this as out of scope:
the project task owner should inspect the library API and adapt the notebook or
project wrapper unless the request explicitly assigns upstream library changes.

This is the same responsibility-scope defect in a concrete external-library
form. AgentCanon needs a gate that distinguishes:

- caller-side use of a dependency's public API;
- project-owned wrapper or notebook cleanup;
- upstream library defect reports;
- explicit upstream library implementation work.

The workflow should require an owner/scope check before proposing edits outside
the active repository surface or before treating a dependency API gap as a
license to modify the dependency.

## 2026-06-07 Triage

This issue remains open after stale-issue triage, but the current integration
branch covers a major slice: `responsibility-scope.toml` gains exclusion and
overlap handling, the responsibility checker covers directory and import
surfaces more directly, and the new `structure-refactor` skill gives directory
responsibility cleanup a routed workflow. The remaining close condition is the
full end-to-end gate across external-library boundary decisions and helper-like
function additions, not only repository directory ownership.

## Resolution

Closed on 2026-06-21.

The responsibility-scope gate, import responsibility gate, helper inventory
gate, and hook regression tests now cover the issue's required boundary set:
top-level responsibility scopes, tool path ownership, issue links, import
rules, unused / wildcard import findings, local scope import crossings,
library-boundary guard behavior, and helper-like addition evidence.

## Validation

- `python3 tools/agent_tools/responsibility_scope.py --root . --format text`
- `python3 tools/agent_tools/import_responsibility.py --root . --format text`
- `python3 tools/agent_tools/helper_function_inventory.py --root . --changed --baseline-ref origin/main --format text`
- `python3 -m pytest tests/agent_tools/test_responsibility_scope.py tests/agent_tools/test_import_responsibility.py tests/agent_tools/test_codex_hooks.py -q`
