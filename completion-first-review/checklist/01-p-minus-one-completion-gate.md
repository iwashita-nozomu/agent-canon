# P-1 Completion Gate Checklist
<!--
@dependency-start
contract reference
responsibility Defines the first-priority completion judgment checklist.
upstream design ../README.md completion-first review index
upstream design ../explanation/00-completion-first-principle.md completion-first rationale
upstream implementation ../../tools/agent_tools/task_close.py current closeout evaluator
@dependency-end
-->

## Reader Map

- Owns the P-1 completion-gate checklist for evidence-backed completion
  judgment.
- Main path: P-1 goal explains the gate, Checklist lists required surfaces, and
  P-1 done condition states the exit criteria.
- Read this when defining or reviewing completion-first closeout gates.
- Boundary: this file is a checklist; the broader completion-first model lives
  in the linked review index and explanation docs.

## P-1 goal

Completion judgment comes first. This checklist defines what must exist before agent settings, workflow rules, and self-growth rules can be considered mechanically meaningful.

## Checklist

### [ ] P-1-001: Definition of Done source

- Target surface: `agents/canonical/DEFINITION_OF_DONE.md`
- Problem: completion rules are scattered across runtime entrypoints, templates, PR checklists, and tools.
- Violation that currently passes: one surface treats `ci-quick` as enough while another implies full CI.
- Action: create one Definition of Done source for all closeout profiles.
- Acceptance: every completion-related workflow or template links back to this source.

### [ ] P-1-002: closeout profiles

- Target surface: `agents/canonical/closeout_profiles.yaml`
- Problem: one fixed closeout rule cannot fit advisory, trivial, standard, strict, self-growth, and release tasks.
- Violation that currently passes: self-growth task closes without negative replay evidence.
- Action: define profile-specific required artifacts, commands, reviewers, and forbidden shortcuts.
- Acceptance: `task_close.py` or a new verifier can resolve a profile and list requirements.

### [ ] P-1-003: manual unlock prohibition

- Target surface: `task_close.py`, `closeout_gate.md`, generated completion report
- Problem: a hand-written unlock field is self-attestation.
- Violation that currently passes: `user_completion_report=unlocked` is written manually.
- Action: make generated verifier output the only authority.
- Acceptance: manual unlock token alone never passes completion.

### [ ] P-1-004: completion verifier chain

- Target surface: `tools/agent_tools/completion_verifier.py`
- Problem: existing checks are separate and not one verdict chain.
- Violation that currently passes: `evaluate_agent_run.py` passes but required profile evidence is missing.
- Action: create a verifier that reads closeout profile and evidence artifacts.
- Acceptance: `completion_verification_report.json` summarizes all sub-verifiers and final verdict.

### [ ] P-1-005: artifact schemas

- Target surface: `agents/templates/artifact_schema.yaml`
- Problem: file existence is not content completeness.
- Violation that currently passes: `schedule.md` exists but has no work units.
- Action: define required sections, fields, and minimum rows for each artifact.
- Acceptance: heading-only artifacts fail.

### [ ] P-1-006: validation evidence schema

- Target surface: `agents/templates/validation_evidence.schema.yaml`
- Problem: pasted command output is not trustworthy.
- Violation that currently passes: old `make ci` output is pasted as current evidence.
- Action: require command, cwd, runtime profile, timestamps, exit code, stdout/stderr hashes, and evidence path.
- Acceptance: validation status without evidence id fails.

### [ ] P-1-007: behavior event schema

- Target surface: `agents/templates/behavior_event.schema.yaml`
- Problem: behavior monitoring uses weak text tokens.
- Violation that currently passes: `tool_call=make ci static_analysis=pass` with no command evidence.
- Action: define event types such as `tool_call`, `skill_invocation`, `runtime_feedback`, `review_decision`, `subagent_lifecycle`.
- Acceptance: schema-invalid behavior event fails strict/self-growth completion.

### [ ] P-1-008: negative fixture policy

- Target surface: `evidence/agent-evals/negative_cases/`
- Problem: discovered false negatives are not automatically replay-tested.
- Violation that currently passes: token-only evidence continues to pass after being noticed once.
- Action: every false negative gets a fixture or an exception.
- Acceptance: self-growth repair without negative case fails unless exception is explicit.

### [ ] P-1-009: convention compliance first

- Target surface: `check_convention_compliance.py`
- Problem: normative rules can be added without verifier routes.
- Violation that currently passes: workflow says “must” but no tool can check it.
- Action: run convention compliance at the start of completion verification.
- Acceptance: normative rule without verifier or non-verifiable rationale fails.

### [ ] P-1-010: PR evidence matrix from profiles

- Target surface: PR templates and closeout profiles
- Problem: PR checkbox requirements can drift from task closeout requirements.
- Violation that currently passes: Docker change marks Docker validation as not affected with no scope reason.
- Action: generate PR evidence matrix from closeout profile.
- Acceptance: PR evidence and closeout verifier requirements match.

### [ ] P-1-011: reviewer independence

- Target surface: closeout profile and review schemas
- Problem: strict review can be self-attested.
- Violation that currently passes: parent marks independent diff-check complete.
- Action: strict/self-growth/release profiles require independent reviewer identity and read-only evidence.
- Acceptance: parent/self review fails strict independent check.

### [ ] P-1-012: generated completion report

- Target surface: `tools/agent_tools/generate_completion_report.py`
- Problem: final user-facing report can contain unsupported claims.
- Violation that currently passes: final response says checks passed without verifier evidence.
- Action: generate completion report from `completion_verification_report.json`.
- Acceptance: final pass claims are copied from verifier output, not written freehand.

## P-1 done condition

P-1 is done when a task can answer all of the following before implementation starts:

- [ ] Which closeout profile applies?
- [ ] Which artifacts are required?
- [ ] Which commands or validators are required?
- [ ] Which reviewer independence conditions are required?
- [ ] Which evidence classes are accepted?
- [ ] Which shortcuts are forbidden?
- [ ] Which tool produces the final completion verdict?
