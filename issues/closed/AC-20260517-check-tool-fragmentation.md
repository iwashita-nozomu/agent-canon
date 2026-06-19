# Check Tool Fragmentation

<!--
@dependency-start
contract issue
responsibility Records the finding that AgentCanon checker entrypoints are too scattered to route reliably.
upstream design ../../tools/README.md documents shared tool entrypoints.
upstream design ../../tools/catalog.yaml defines structured tool ownership.
upstream design ../../documents/tools/README.md documents user-facing tool groups.
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates scope-to-tool ownership.
downstream implementation ../../tools/agent_tools/tool_drift.py validates checker trace wiring.
@dependency-end
-->

issue_id: AC-20260517-check-tool-fragmentation
status: resolved
source: user
severity: S1
evidence: User feedback on 2026-05-17: check tools are scattered and should be treated as an operational issue.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/253
affected_surfaces: tools/catalog.yaml, tools/README.md, documents/tools/README.md, tools/agent_tools/tool_catalog.py, tools/agent_tools/tool_drift.py, tools/ci/run_all_checks.sh, .github/workflows/agent-canon-static-gates.yml
edit_scope: responsibility-scope.toml, tools/catalog.yaml, tools/README.md, documents/tools/README.md, documents/responsibility-scope-management.md, tools/agent_tools/responsibility_scope.py, tests/agent_tools/test_responsibility_scope.py
required_action: Add a responsibility-scope map that ties checker tools to owned surfaces and wire that map into lightweight gates.
close_condition: A machine check can list which scope owns each checker family and fails when a default checker lacks a scope/tool contract.
resolved_by: PR #75 and the current responsibility-scope integration; this finding is subsumed by AC-20260517-responsibility-scope-management and the checker/tool catalog route.
resolved_at: 2026-06-07

## Finding

AgentCanon already has many checkers, but the routing surface is split between
`tools/catalog.yaml`, workflow scripts, PR templates, and narrative docs. This
makes it too easy for an agent to add one more checker without explaining which
runtime or repository responsibility it protects.

## Required Fix

Introduce a responsibility-scope manifest and checker. Tool additions must be
classifiable by owned surface, and PR/static gates should run the checker so
new checkers cannot remain orphaned.
