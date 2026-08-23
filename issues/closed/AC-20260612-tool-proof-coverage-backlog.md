# Tool Proof Coverage Backlog

<!--
@dependency-start
contract issue
responsibility Tracks the backlog to turn tool proof coverage into full Lean verification.
upstream implementation ../../tools/agent_tools/tool_proof_coverage.py reports per-tool proof coverage.
upstream design ../../documents/tools/tool_proof_coverage.md documents strict Lean verification mode.
upstream design ../../tools/catalog.yaml lists cataloged AgentCanon tools.
@dependency-end
-->

issue_id: AC-20260612-tool-proof-coverage-backlog
status: wontfix
resolved_by: GitHub issue #544; G5 proof-policy simplification branch
resolved_at: 2026-08-08
source: user
severity: S1
evidence: Universal Lean proof coverage was superseded by the selected-proof contract; unverified rows remain honest observational evidence.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/244
affected_surfaces: tools/catalog.yaml, tools/agent_tools/tool_proof_coverage.py, documents/tools/tool_proof_coverage.md, tests/agent_tools/test_tool_proof_coverage.py
edit_scope: none; retain selected proof metadata only when a real contract requires it
required_action: none; superseded by issue #544, retain selected proof checks only.
close_condition: universal backlog retired and superseded by issue #544; selected checks remain operational.

## Finding

The former universal strict invocation is retired. The checker now requires
explicit `--tool-id` selection before strict proof validation.

Observed on 2026-06-12:

- `TOOL_PROOF_COVERAGE_TOOLS=106`
- `TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED=0`
- `TOOL_PROOF_COVERAGE_PERFORMANCE_LEAN_VERIFIED=0`
- `TOOL_PROOF_COVERAGE_FINDINGS=212`

## Required Closure

For a selected `tools/catalog.yaml` entry:

1. Define the intended behavior model.
1. Define the performance or cost model, including explicit external runtime
   assumptions where the tool delegates to another process or backend.
1. Add checked Lean artifacts for `proofs.behavior` and `proofs.performance`.
1. Record the theorem, artifact, checker command, and `checked: true` metadata.
1. Run `python3 tools/agent_tools/tool_proof_coverage.py --tool-id <id> --require-lean-verified`.

No universal proof completion claim is made for unselected tools.
