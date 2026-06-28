# Implementation Roadmap
<!--
@dependency-start
contract reference
responsibility Provides a phased implementation roadmap for the completion-first AgentCanon review.
upstream design ../README.md completion-first review index
upstream design 01-priority-layers.md revised priority layers
upstream design 03-evidence-and-closeout.md closeout evidence design
@dependency-end
-->

## Reader Map

Use this roadmap to answer which completion-first improvements should be built
in which phase and how report-only checks graduate to strict gates. Read the
roadmap principle first, then the sprint sections in order from completion
definition through audit and retirement. The final sections identify suggested
first PRs and the migration rule that keeps completion evidence ahead of
runtime tuning.

## Roadmap principle

Do not turn every proposal into a hard gate immediately. Introduce each mechanical check in three phases:

1. **Report-only**: generate artifacts and warnings.
2. **Strict-required**: fail strict, self-growth, or release profiles.
3. **Standard-candidate**: consider broader adoption after false positives are understood.

This reduces disruption while still moving toward stronger completion judgment.

## Sprint 1: Completion definition

Create the completion-first surfaces:

- `agents/canonical/DEFINITION_OF_DONE.md`
- `agents/canonical/closeout_profiles.yaml`
- `agents/templates/artifact_schema.yaml`
- `agents/templates/behavior_event.schema.yaml`
- `agents/templates/validation_evidence.schema.yaml`

Acceptance:

- advisory, trivial, standard, strict, self_growth, and release profiles exist,
- each profile lists required artifacts,
- each profile lists forbidden shortcuts,
- manual unlock is not authoritative,
- profile requirements can be rendered as a Markdown matrix.

## Sprint 2: Completion verifier skeleton

Create:

- `tools/agent_tools/completion_verifier.py`
- `tools/agent_tools/validate_artifact_schema.py`
- `tools/agent_tools/validate_behavior_events.py`
- `tools/agent_tools/record_validation_evidence.py`

Acceptance:

- verifier can read a profile,
- verifier can report missing artifacts,
- verifier can reject schema-invalid artifacts,
- verifier can reject token-only validation evidence,
- verifier writes `completion_verification_report.json`.

## Sprint 3: Closeout integration

Update `task_close.py` so it can delegate to or consume completion verifier output.

Acceptance:

- `task_close.py --profile self_growth` exists or equivalent profile resolution exists,
- manual `user_completion_report=unlocked` is not authoritative,
- generated completion verdict is the source of truth,
- legacy closeout artifacts remain readable during migration.

## Sprint 4: Behavior evidence hardening

Update monitoring and evaluation:

- workflow monitoring may still be Markdown, but machine events should become JSONL or schema-parseable lines,
- tool calls require command-backed evidence,
- skill invocation requires source path and use evidence,
- runtime feedback requires type and target.

Acceptance:

- token-only behavior fixtures fail,
- tool_call without evidence path fails,
- runtime_feedback without self-growth route fails under self_growth profile.

## Sprint 5: MCP and goal loop honesty

Add:

- `mcp_status.md` or JSON equivalent,
- MCP capability catalog,
- alternate route evidence policy,
- goal snapshot requirements.

Acceptance:

- MCP pass, fail, alternate route, and not-applicable are distinct,
- goal-driven task cannot close while `NEXT_ACTION=run_next_iteration`,
- ignored/local `goal.md` has a reviewable run-bundle snapshot,
- repeated MCP failure can become self-growth feedback.

## Sprint 6: Self-growth manifest and replay

Add:

- self-growth repair manifest template,
- negative case registry,
- replay tool skeleton,
- promotion/retirement decision template.

Acceptance:

- runtime feedback in self-growth profile requires repair manifest,
- tool gaps cannot be closed by prompt repair alone,
- prompt repair requires eval rerun,
- every self-growth repair has a negative case or explicit exception.

## Sprint 7: Surface ownership and sync

Add:

- changed path surface classifier,
- root symlink view direct-edit rejection,
- synced-copy source hash status,
- remote status report.

Acceptance:

- unknown surface fails strict completion,
- direct root view edit fails,
- synced copy hash mismatch fails,
- AgentCanon source changes require upstream evidence.

## Sprint 8: Workflow and skill contracts

Add machine-readable contract blocks.

Acceptance:

- every public workflow has required artifacts and forbidden shortcuts,
- every public skill has use / do-not-use / escalation fields,
- skill shim and human doc critical concept coverage is checked,
- overlay selection can be validated against routing decisions.

## Sprint 9: Template and PR propagation

Update Template-facing surfaces later, after the completion core is stable.

Acceptance:

- PR evidence matrix is generated from closeout profiles,
- bootstrap unresolved-token scan exists,
- Docker profile selection is explicit,
- devcontainer secret mounts are dynamic,
- audit profiles are executable.

## Sprint 10: Audit and retirement

Add the cleanup loop.

Acceptance:

- growth metrics exist,
- learning items have review-after or retirement policy,
- duplicate rules are reported,
- compatibility wrappers have deprecation lifecycle.

## Suggested first PRs

1. Add Definition of Done and closeout profile draft.
2. Add completion verifier skeleton in report-only mode.
3. Add behavior event schema and negative fixtures for token-only pass cases.
4. Add self-growth repair manifest template.
5. Add surface classification report-only tool.

## Completion-first migration rule

During migration, a task can use old closeout artifacts only if it also records which new profile it would have used. This prevents the transition from becoming another ambiguous state.
