# Violation Fixture Checklist
<!--
@dependency-start
contract reference
responsibility Defines how false-negative cases become replayable fixtures for completion-first AgentCanon improvements.
upstream design ../README.md completion-first review index
upstream design ../explanation/04-violation-cases.md false-negative catalog
upstream design 01-p-minus-one-completion-gate.md completion gate checklist
@dependency-end
-->

## Reader Map

Use this checklist to convert completion false negatives into replayable
fixtures. Read Purpose and Fixture requirements first to understand the fixture
schema, then use Required fixture categories to choose the matching negative
case. Fixture lifecycle and the completion-first invariant explain how cases
move from warning to regression evidence.

## Purpose

A violation case is not only a warning. It should become a fixture that the repo can run. This checklist converts false-negative cases into regression tests for AgentCanon behavior.

## Fixture requirements

Each fixture should include:

```yaml
id: V001
title: token-only static analysis pass
fixture_type: run_bundle | workflow_doc | skill_doc | repo_surface | pr_body | experiment_run
target_profile: strict | self_growth | release | standard
expected_old_status: pass_or_unknown
expected_new_status: fail
failure_reason: tool_call event lacks command-backed evidence
repair_surface: behavior_event.schema.yaml
positive_fixture: V001_positive
```

## Required fixture categories

### [ ] VF-001: token-only evidence fixture

- Represents: pass tokens with no command-backed evidence.
- Should fail when: behavior event schema is enforced.
- Positive case: command-backed evidence with exit code and hashes.

### [ ] VF-002: manual unlock fixture

- Represents: hand-written `user_completion_report=unlocked`.
- Should fail when: generated completion verifier report is required.
- Positive case: completion report generated from verifier result.

### [ ] VF-003: MCP false pass fixture

- Represents: MCP unavailable but recorded as pass.
- Should fail when: MCP status artifact is required.
- Positive case: MCP pass artifact or accepted shell alternate route artifact.

### [ ] VF-004: runtime feedback without self-growth fixture

- Represents: feedback recorded only in retrospective.
- Should fail when: self-growth repair manifest is required.
- Positive case: feedback maps to diagnosis, repair, eval, replay, and promotion decision.

### [ ] VF-005: prompt repair without eval fixture

- Represents: skill/workflow prompt edited but eval not rerun.
- Should fail when: prompt repair requires baseline and rerun eval IDs.
- Positive case: same eval ID is rerun and passes.

### [ ] VF-006: tool-gap prompt-only repair fixture

- Represents: mechanical false negative fixed only by prose warning.
- Should fail when: tool-gap categories require tool/schema/eval repair.
- Positive case: verifier or schema updated and negative fixture fails.

### [ ] VF-007: memory dirty fixture

- Represents: memory changed inside AgentCanon submodule but not committed/pushed.
- Should fail when: memory propagation gate is active.
- Positive case: AgentCanon commit/push and superproject pin evidence exist.

### [ ] VF-008: root view direct edit fixture

- Represents: root symlink view edited directly.
- Should fail when: surface classification is active.
- Positive case: source surface edited and root view synced.

### [ ] VF-009: synced-copy drift fixture

- Represents: root copied workflow differs from source without source update.
- Should fail when: source hash is checked.
- Positive case: source hash matches or source update is included.

### [ ] VF-010: review self-approval fixture

- Represents: parent marks independent review complete.
- Should fail when: reviewer independence is required.
- Positive case: separate reviewer identity and read-only evidence.

### [ ] VF-011: heading-only artifact fixture

- Represents: required artifact exists with headings only.
- Should fail when: artifact schema requires minimum content.
- Positive case: required sections and rows are present.

### [ ] VF-012: goal still active fixture

- Represents: goal loop says continue but task emits completion.
- Should fail when: goal status blocks completion.
- Positive case: `NEXT_ACTION=close_goal_loop` and remaining gates pass.

### [ ] VF-013: debug run claim fixture

- Represents: debug experiment result supports durable claim.
- Should fail when: claim ledger requires formal run.
- Positive case: formal run with comparison allowed.

### [ ] VF-014: missing overlay fixture

- Represents: hypothesis-heavy change without hypothesis-validation overlay.
- Should fail when: routing decision validator is active.
- Positive case: overlay selected or rejected with reason.

### [ ] VF-015: stale remote fixture

- Represents: local mirror treated as canonical remote.
- Should fail when: remote status artifact is required.
- Positive case: GitHub main, local mirror, proposal branch, and submodule pin are distinct.

## Fixture lifecycle

For each fixture:

- [ ] Write negative fixture.
- [ ] Record expected old status.
- [ ] Add verifier rule.
- [ ] Confirm negative fixture fails.
- [ ] Write positive fixture.
- [ ] Confirm positive fixture passes.
- [ ] Add fixture to self-growth or strict profile suite.
- [ ] Document repair surface.

## Completion-first invariant

```text
A known false negative is unresolved until it is represented by a failing fixture or explicitly classified as not fixture-representable.
```
