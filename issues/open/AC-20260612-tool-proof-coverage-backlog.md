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
status: in_progress
source: user
severity: S1
evidence: User requested Lean proof of performance and intended behavior for all tools on 2026-06-12; strict tool proof coverage reports zero checked Lean proofs.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/244
affected_surfaces: tools/catalog.yaml, tools/agent_tools/tool_proof_coverage.py, documents/tools/tool_proof_coverage.md, tests/agent_tools/test_tool_proof_coverage.py
edit_scope: per-tool Lean proof artifacts, tools/catalog.yaml proof metadata, tool_proof_coverage strict mode evidence
required_action: Add checked Lean behavior and performance proof metadata for every cataloged AgentCanon tool.
close_condition: `python3 tools/agent_tools/tool_proof_coverage.py --require-lean-verified` passes for all cataloged tools.

## Finding

`tools/agent_tools/tool_proof_coverage.py --require-lean-verified` currently
fails because no cataloged AgentCanon tool has checked Lean behavior and
performance proof metadata.

Observed on 2026-06-12:

- `TOOL_PROOF_COVERAGE_TOOLS=106`
- `TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED=0`
- `TOOL_PROOF_COVERAGE_PERFORMANCE_LEAN_VERIFIED=0`
- `TOOL_PROOF_COVERAGE_FINDINGS=212`

## Required Closure

For each `tools/catalog.yaml` entry:

1. Define the intended behavior model.
1. Define the performance or cost model, including explicit external runtime
   assumptions where the tool delegates to another process or backend.
1. Add checked Lean artifacts for `proofs.behavior` and `proofs.performance`.
1. Record the theorem, artifact, checker command, and `checked: true` metadata.
1. Run `python3 tools/agent_tools/tool_proof_coverage.py --require-lean-verified`.

This issue closes only when strict mode passes for all cataloged tools.
