# Priority Order Checklist
<!--
@dependency-start
contract reference
responsibility Lists the corrected completion-first priority order for AgentCanon improvements.
upstream design ../README.md completion-first review index
upstream design ../explanation/00-completion-first-principle.md completion-first rationale
@dependency-end
-->

## Corrected order

- [ ] **P-1: Completion judgment rules and completion-verifier tooling**
  - Definition of Done exists.
  - closeout profiles exist.
  - verifier authority is clear.
  - manual unlock is not authoritative.
  - evidence schemas exist.

- [ ] **P0: Agent settings and runtime invariants**
  - Runtime settings serve completion profiles.
  - Agent modes do not weaken gate profiles.
  - Role write policies are enforceable.

- [ ] **P1: Tool, evidence, and verifier implementation**
  - Tool outputs are evidence-backed.
  - Behavior events are schema-valid.
  - Validation evidence includes command metadata.

- [ ] **P2: MCP, goal loop, and alternate route evidence**
  - MCP pass/fail/alternate route/not-applicable are separate.
  - goal loop status controls closeout for goal-driven work.

- [ ] **P3: Self-growth state machine**
  - Feedback becomes diagnosis.
  - Diagnosis becomes repair.
  - Repair is evaled and replayed.
  - Stable learning is promoted or explicitly not promoted.

- [ ] **P4: Surface ownership and AgentCanon sync**
  - Changed paths have owners.
  - Root view edits are rejected.
  - Synced copies match source.
  - Submodule changes propagate correctly.

- [ ] **P5: Workflow and skill contracts**
  - Workflows expose required artifacts and commands.
  - Skills expose use and do-not-use conditions.
  - Skill invocation is usage-backed.

- [ ] **P6: Template bootstrap, Docker, CI, and PR evidence**
  - Derived repos inherit completion profiles.
  - PR evidence matrix is generated from profiles.

- [ ] **P7: Research, experiment, claim, and docs rigor**
  - Claims map to formal evidence.
  - Long-form docs have contradiction checks.

- [ ] **P8: Audit, metrics, and retirement**
  - Growth metrics exist.
  - Old rules can retire.

## Gate ordering rule

- [ ] Do not start with agent settings unless P-1 has at least a draft.
- [ ] Do not start with workflow prose unless a verifier path exists.
- [ ] Do not start with memory promotion unless self-growth completion requirements exist.
- [ ] Do not use token-efficiency work to weaken completion requirements.

## Review question

For every proposed change, ask:

> Which completion profile will this help satisfy, and which verifier will detect success or failure?
