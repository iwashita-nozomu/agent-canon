# P3 Self-Growth Checklist
<!--
@dependency-start
contract reference
responsibility Defines the self-growth checklist for completion-first AgentCanon improvements.
upstream design ../README.md completion-first review index
upstream design ../explanation/02-self-growth-state-machine.md self-growth state machine
upstream design ../../agents/workflows/agent-learning-workflow.md agent learning workflow
upstream design ../../agents/workflows/adaptive-improvement-workflow.md adaptive improvement workflow
@dependency-end
-->

## Reader Map

- Owns the P3 checklist for AgentCanon self-growth and runtime feedback
  improvement.
- Main path: Scope defines when P3 starts, Checklist enumerates required
  capabilities, and P3 done condition states completion.
- Read this when implementing or reviewing self-growth, feedback taxonomy, or
  adaptive improvement evidence.
- Boundary: this checklist records completion criteria; detailed workflows live
  in the linked agent-learning and adaptive-improvement docs.

## Scope

P3 makes AgentCanon able to improve itself without turning every observation into permanent prose. It starts after completion profiles, evidence schemas, and MCP/goal status are defined.

## Checklist

### [ ] P3-001: runtime feedback taxonomy

- Target: workflow monitoring and behavior event schema.
- Problem: feedback is currently too easy to record as unclassified prose.
- Violation: a tool-gap failure is handled as a prompt preference.
- Action: require `feedback_type`, `severity`, `source`, `target`, and `evidence`.
- Acceptance: unclassified feedback fails self-growth completion.

### [ ] P3-002: learning diagnosis artifact

- Target: `learning_diagnosis.md` or equivalent YAML.
- Problem: observation and repair are not connected by root-cause analysis.
- Violation: “be more thorough” is added to memory without identifying failed invariant.
- Action: require failed invariant, root-cause category, and why-not-other-causes.
- Acceptance: self-growth repair without diagnosis fails.

### [ ] P3-003: self-growth repair manifest

- Target: `self_growth_repair_manifest.yaml`.
- Problem: repair details are scattered across prompt, workflow, memory, eval, and tool changes.
- Action: record trigger, diagnosis, repair, eval, replay, promotion, and retirement.
- Acceptance: every runtime feedback item maps to a repair manifest entry.

### [ ] P3-004: prompt repair requires eval rerun

- Target: prompt eval tooling.
- Problem: prompt changes can be made without proving they address the failure.
- Violation: a skill file is edited, but the relevant eval is not rerun.
- Action: require baseline and rerun eval IDs.
- Acceptance: rerun eval IDs match the baseline eval IDs unless explicitly justified.

### [ ] P3-005: tool gaps cannot close with prompt-only repair

- Target: self-growth closeout profile.
- Problem: mechanical false negatives can be hidden by prose warnings.
- Violation: token-only evidence problem is fixed by adding “do not fake evidence” to a workflow doc.
- Action: require tool, schema, or eval repair for `tool_gap` and `false_negative_gate`.
- Acceptance: prompt-only repair fails for tool-gap categories.

### [ ] P3-006: negative fixture required

- Target: `evidence/agent-evals/negative_cases/`.
- Problem: discovered false negatives are not replay-tested.
- Action: add a fixture representing the old failure.
- Acceptance: negative fixture fails under new verifier.

### [ ] P3-007: positive replay required

- Target: replay fixtures.
- Problem: overcorrection can break valid workflows.
- Action: add a positive fixture for the accepted path.
- Acceptance: positive fixture passes under new verifier.

### [ ] P3-008: memory propagation gate

- Target: `memory/`, AgentCanon submodule, superproject pin.
- Problem: memory changes can stay local and fail to propagate.
- Violation: `memory/AGENT_PHILOSOPHY.md` is edited but AgentCanon upstream is not updated.
- Action: require AgentCanon commit/push and superproject pin evidence when memory changes.
- Acceptance: memory dirty state fails self-growth completion.

### [ ] P3-009: promotion criteria

- Target: promotion decision artifact.
- Problem: one-off observations can become repo-wide rules.
- Action: require scope, support count or explicit durable user instruction, and counterexample review.
- Acceptance: repo-wide promotion without scope and support fails.

### [ ] P3-010: retirement policy

- Target: memory and workflow rules.
- Problem: canon grows but does not shrink.
- Action: every durable learning item has `review_after`, `expiry`, `superseded_by`, or no-retirement rationale.
- Acceptance: retirement sweep can identify stale items.

### [ ] P3-011: growth metrics

- Target: `growth_metrics.json`.
- Problem: learning is not measured.
- Action: track replay pass rate, unresolved feedback count, false-negative reduction, and duplicate rule count.
- Acceptance: self-growth closeout includes updated metrics.

### [ ] P3-012: feedback precedence

- Target: self-growth workflow.
- Problem: user feedback, reviewer feedback, token efficiency, and tool failures may conflict.
- Action: define precedence order and conflict artifact.
- Acceptance: unresolved conflict blocks self-growth completion.

### [ ] P3-013: static-analysis feedback routing

- Target: behavior eval and self-growth manifest.
- Problem: static-analysis findings can be recorded without repair target.
- Action: route findings to code fix, workflow/prompt repair, eval update, or no-op reason.
- Acceptance: `static_analysis_feedback=pending` fails.

### [ ] P3-014: run-path comparison as repair input

- Target: `compare_agent_run_paths.py` or successor.
- Problem: inefficient path selection is only a token.
- Action: compare trace sequences, route cost, and selected path.
- Acceptance: selected inefficient route requires prompt/workflow/tool repair.

## P3 done condition

- [ ] Feedback is typed.
- [ ] Root cause is diagnosed.
- [ ] Repair surface is justified.
- [ ] Eval is rerun.
- [ ] Negative and positive replay cases exist.
- [ ] Promotion or no-promotion is explicit.
- [ ] Retirement or review-after policy exists.
- [ ] Memory changes propagate to AgentCanon when durable.
