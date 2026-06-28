# Evidence And Closeout
<!--
@dependency-start
contract reference
responsibility Explains evidence quality and closeout verifier requirements for completion-first AgentCanon improvements.
upstream design ../README.md completion-first review index
upstream design 00-completion-first-principle.md completion-first rationale
upstream implementation ../../tools/agent_tools/task_close.py current closeout evaluator
upstream implementation ../../tools/agent_tools/evaluate_agent_run.py current run evaluator
upstream implementation ../../tools/agent_tools/workflow_monitor.py current monitoring helper
@dependency-end
-->

## Reader Map

Use this document to answer which evidence classes can support completion-first
closeout and which evidence is too weak to unlock completion. Read the evidence
hierarchy first, then the closeout verifier chain and artifact schema examples
for implementation shape. The final sections explain why preset closeout tokens
are dangerous, how completion reports are generated, which failures must be
rejected, minimum artifacts by profile, and the invariant.

## Why evidence needs a hierarchy

A completion system fails if it treats all evidence as equal. A checkbox, a pass token, a pasted command output, and a command-backed artifact should not have the same weight.

The completion-first design should make evidence quality explicit.

## Evidence classes

### Class 0: Unsupported claim

Examples:

- `make ci passed` written in prose,
- `validation_complete=yes` with no command evidence,
- `mcp_inventory=pass` with no MCP report,
- `review approved` with no reviewer identity or diff ref.

Class 0 is not accepted for completion.

### Class 1: Manual structured claim

Examples:

- checked PR template item,
- closeout key set by hand,
- Markdown section with a status value.

Class 1 can guide humans but should not unlock completion.

### Class 2: Structured artifact

Examples:

- `schedule.md` with required work units,
- `work_log.md` with chronological entries,
- `routing_decision.yaml`,
- `surface_classification.json`,
- `self_growth_repair_manifest.yaml`.

Class 2 can satisfy artifact requirements if schema-valid.

### Class 3: Command-backed evidence

Examples:

```yaml
command: make ci
cwd: /workspace
runtime_profile: docker-default
started_at: "2026-05-10T12:00:00+09:00"
completed_at: "2026-05-10T12:03:00+09:00"
exit_code: 0
stdout_sha256: "..."
stderr_sha256: "..."
evidence_path: reports/agents/<run>/validation/make-ci.log
```

Class 3 should be required for validation in strict, self-growth, and release profiles.

### Class 4: Independent review evidence

Examples:

- reviewer identity,
- reviewer role,
- diff ref,
- read-only flag,
- finding IDs,
- finding status,
- fix evidence path.

Class 4 should be required for independent diff-check and strict reviews.

### Class 5: Replay evidence

Examples:

- negative fixture fails,
- positive fixture passes,
- before/after eval result,
- replay command evidence.

Class 5 should be required for self-growth.

## Closeout verifier chain

A completion-first closeout should use a chain like:

```text
profile resolver
  -> requirement generator
  -> artifact schema verifier
  -> behavior event verifier
  -> validation evidence verifier
  -> review independence verifier
  -> self-growth verifier
  -> final completion verdict
```

The final verdict should be written to:

- `completion_verification_report.json`,
- optionally `completion_report.md` generated from the JSON.

## Artifact schema examples

### schedule artifact

```yaml
artifact: schedule.md
required_sections:
  - Work Units
  - Gate Plan
  - Validation Plan
minimum_rows:
  Work Units: 1
required_fields:
  Work Units:
    - id
    - description
    - owner
    - status
```

### review findings artifact

```yaml
artifact: review_findings.yaml
required_fields:
  - finding_id
  - severity
  - status
  - reviewer_role
  - diff_ref
  - fix_evidence_path
forbidden:
  - severity: fix-now
    status: open
```

### behavior event artifact

```yaml
event_type: tool_call
required_fields:
  - command
  - cwd
  - runtime_profile
  - exit_code
  - evidence_path
  - stdout_sha256
  - stderr_sha256
```

## Why closeout-token-preset is dangerous

A preset helper can be useful, but it must not create authoritative pass evidence.

Bad pattern:

```text
workflow_monitor.py --closeout-token-preset
```

and then closeout passes because standard pass tokens were inserted.

Better pattern:

```text
workflow_monitor.py --closeout-claim-preset
```

This may create claims such as:

```text
tool_call_claim=make ci
review_claim=independent diff-check required
```

But actual pass tokens must come from verifier tools that inspect evidence.

## Completion report generation

The user-facing completion report should be generated from verifier output.

The report should include:

- selected closeout profile,
- required evidence summary,
- pass/fail status for each verifier,
- skipped checks and their accepted reasons,
- residual risk,
- links to evidence artifacts,
- statement of what was not done.

It should not include unverified pass claims.

## Failure examples that must be rejected

The following should fail strict or self-growth completion:

1. `make ci passed` with no command evidence.
2. `mcp_inventory=pass` without MCP report or alternate route report.
3. `diff_check_agent_complete=yes` with reviewer role equal to parent/self.
4. `runtime_feedback=observed` without self-growth repair manifest.
5. `prompt_eval=pass` without eval ID and rerun evidence.
6. `memory changed` without AgentCanon commit/push and superproject pin evidence.
7. `schedule.md` exists but has no work units.
8. `review approved` but fix-now findings remain open.
9. `goal.md` says active but completion is emitted.
10. `debug` experiment run supports a durable claim.

## Minimum closeout artifacts by profile

| Profile | Minimum artifacts |
| --- | --- |
| advisory | answer/routing summary, no fake repo validation |
| trivial | request trace, changed file summary, targeted validation |
| standard | routing decision, schedule, work log, validation evidence, closeout gate |
| strict | standard + surface classification, dependency review, static analysis, independent review |
| self_growth | strict + repair manifest, diagnosis, eval, replay, promotion/retirement decision |
| release | strict + remote status, pin evidence, fresh clone evidence, PR evidence matrix |

## Completion-first invariant

```text
If a required artifact is present but schema-invalid, it is missing for completion purposes.
```

This prevents empty files and status-only files from acting as completion evidence.
