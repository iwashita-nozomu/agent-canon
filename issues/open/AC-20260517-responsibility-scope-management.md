# Responsibility Scope Management

<!--
@dependency-start
responsibility Records the finding that AgentCanon lacks a machine-readable responsibility scope map.
upstream design ../../documents/SHARED_RUNTIME_SURFACES.md defines shared runtime surface ownership.
upstream design ../../documents/shared-runtime-surfaces.toml defines shared surface classes.
upstream design ../../tools/catalog.yaml defines tool ownership.
downstream design ../../responsibility-scope.toml defines repo-local scope ownership.
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates scope ownership.
@dependency-end
-->

issue_id: AC-20260517-responsibility-scope-management
status: in_progress
source: user
severity: S1
evidence: User feedback on 2026-05-17: responsibility boundaries and tool responses remain weak and need a management tool.
affected_surfaces: documents/SHARED_RUNTIME_SURFACES.md, documents/shared-runtime-surfaces.toml, responsibility-scope.toml, tools/catalog.yaml, tools/README.md, documents/tools/README.md, .codex/hooks.json, .codex/hooks/library_implementation_guard.py, .codex/hooks/helper_first_guard.py, ROOT_AGENTS.md, agents/workflows/agent-canon-pr-workflow.md
edit_scope: responsibility-scope.toml, documents/templates/responsibility-scope.template.toml, documents/responsibility-scope-management.md, documents/coding-conventions-python.md, tools/agent_tools/responsibility_scope.py, tools/agent_tools/import_responsibility.py, .codex/hooks/library_implementation_guard.py, .codex/hooks/helper_first_guard.py, tests/agent_tools/test_responsibility_scope.py, tests/agent_tools/test_import_responsibility.py, tests/agent_tools/test_codex_hooks.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, tools/ci/run_all_checks.sh
required_action: Add a machine-readable responsibility scope manifest and checker so tools, issues, evals, memory, GitHub surfaces, shared runtime paths, local Python import boundaries, external dependency implementations, and helper-first implementation drift have explicit owners and gates.
close_condition: Checkers validate required top-level responsibility scopes, owner classes, matching tool paths, issue links, import rules, unused imports, wildcard imports, local scope import crossings, direct library implementation rewrites, and helper-like function additions without ownership evidence.

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
