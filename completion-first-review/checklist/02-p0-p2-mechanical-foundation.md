# P0-P2 Mechanical Foundation Checklist
<!--
@dependency-start
contract reference
responsibility Defines the mechanical-foundation checklist after completion judgment is defined.
upstream design ../README.md completion-first review index
upstream design 01-p-minus-one-completion-gate.md completion gate checklist
upstream design ../explanation/01-priority-layers.md priority layer explanation
@dependency-end
-->

## Reader Map

Use this checklist after P-1 has defined completion profiles and initial
Definition of Done surfaces. Read Scope first, then work through P0 runtime
invariants, P1 evidence and verifier tooling, and P2 MCP / goal-loop completion
connections. The done condition states when this mechanical foundation is ready
for later completion-first layers.

## Scope

This checklist starts only after P-1 has at least a draft Definition of Done and closeout profiles. P0-P2 make those completion profiles executable through agent settings, evidence tools, and MCP/goal-loop status.

## P0: agent settings and runtime invariants

### [ ] P0-001: runtime configuration matrix

- Target: `.codex/config.toml`, runtime entrypoints, agent config.
- Problem: runtime settings are scattered across config and prose.
- Action: create `runtime_config_matrix.yaml`.
- Acceptance: Codex, GitHub Actions, and local shell surfaces list their entrypoint, profile support, MCP support, secret mounts, and closeout profile implications.

### [ ] P0-002: closeout profile in task catalog

- Target: `agents/task_catalog.yaml`.
- Problem: task family does not mechanically select completion profile.
- Action: add `default_closeout_profile` and `allowed_closeout_profiles`.
- Acceptance: bootstrap output includes resolved `CLOSEOUT_PROFILE`.

### [ ] P0-003: agent mode vs gate profile separation

- Target: `.codex/config.toml`, token profiles, task catalog.
- Problem: token-lite or spark-worker mode can be confused with lighter correctness gates.
- Action: document and enforce that agent mode affects execution strategy, not completion requirements.
- Acceptance: token profile cannot remove required closeout evidence.

### [ ] P0-004: role write policy enforcement

- Target: `agents/agents_config.json`, behavior events, changed-path evidence.
- Problem: artifact-only roles can accidentally become file writers.
- Action: record role, write scope, and changed paths.
- Acceptance: artifact-only role changing implementation files fails strict completion.

### [ ] P0-005: subagent lifecycle policy

- Target: task catalog and run bundle.
- Problem: fresh subagent requirements are prose-based.
- Action: create `subagent_lifecycle_policy.yaml` and event schema.
- Acceptance: reuse across tasks is rejected unless same-scope continuation is explicit.

### [ ] P0-006: request mode classifier

- Target: bootstrap/task-start tooling.
- Problem: advisory, trivial, standard, strict, and self-growth tasks can be conflated.
- Action: create request-mode resolution artifact.
- Acceptance: repo-changing work cannot start with advisory-only route.

## P1: tool, evidence, and verifier implementation

### [ ] P1-001: validation evidence recorder

- Target: new `record_validation_evidence.py`.
- Problem: pasted output is not trusted evidence.
- Acceptance: validation command evidence includes command, runtime profile, exit code, and hashes.

### [ ] P1-002: behavior event validator

- Target: `validate_behavior_events.py`.
- Problem: token-only behavior monitoring can pass.
- Acceptance: schema-invalid event fails strict/self-growth completion.

### [ ] P1-003: artifact schema validator

- Target: `validate_artifact_schema.py`.
- Problem: empty artifacts pass file-existence checks.
- Acceptance: heading-only `schedule.md`, `work_log.md`, or `review_findings.yaml` fails.

### [ ] P1-004: profile-aware task close

- Target: `task_close.py`.
- Problem: one fixed closeout rule cannot fit all task types.
- Acceptance: `task_close.py --profile self_growth` or equivalent profile resolution exists.

### [ ] P1-005: evidence graph

- Target: `evidence_graph.json`.
- Problem: commands, reviews, artifacts, and closeout keys are disconnected.
- Acceptance: each required closeout key maps to evidence nodes.

### [ ] P1-006: review finding lifecycle

- Target: review artifacts.
- Problem: review approval can hide unresolved findings.
- Acceptance: every fix-now finding maps to fix evidence or accepted rejection rationale.

### [ ] P1-007: diff-check independence

- Target: diff-check artifacts.
- Problem: self-review can be mistaken for independent review.
- Acceptance: strict profile rejects parent/self diff-check approval.

### [ ] P1-008: tool catalog consuming profiles

- Target: `tools/catalog.yaml`.
- Problem: tool exists but no profile consumes it.
- Acceptance: profile-required tools and catalog entries cross-reference each other.

## P2: MCP and goal-loop completion connection

### [ ] P2-001: honest MCP status

- Target: `mcp_status.md` or equivalent JSON.
- Problem: pass/fail/alternate route/not-applicable can be conflated.
- Acceptance: MCP unavailable state cannot be recorded as pass.

### [ ] P2-002: alternate route command policy

- Target: MCP docs/config.
- Problem: MCP alternate route can become ad hoc shell work.
- Acceptance: alternate route command is allowed by profile and evidence is recorded.

### [ ] P2-003: goal loop controls completion

- Target: `goal_loop.py`, closeout profile.
- Problem: task can close while goal loop still says continue.
- Acceptance: `NEXT_ACTION=run_next_iteration` fails self-growth completion.

### [ ] P2-004: goal snapshot

- Target: run bundle.
- Problem: local or ignored `goal.md` is not reviewable.
- Acceptance: goal-driven tasks include `goal_status.md` and `goal_work_breakdown.md` in the run bundle.

### [ ] P2-005: MCP capability catalog

- Target: `mcp_capabilities.yaml`.
- Problem: server implementation and docs can drift.
- Acceptance: configured tools, documented tools, and server capabilities match.

### [ ] P2-006: repeated MCP failure to self-growth

- Target: workflow monitoring and self-growth manifest.
- Problem: recurring MCP failure is treated only as a local blocker.
- Acceptance: repeated MCP failure becomes `feedback_type=tool_gap`.

## P0-P2 done condition

- [ ] Completion profile resolves at task start.
- [ ] Runtime config serves that profile.
- [ ] Required tools produce evidence artifacts.
- [ ] MCP status is honest.
- [ ] Goal-loop status can block completion.
- [ ] Token-only evidence is rejected.
