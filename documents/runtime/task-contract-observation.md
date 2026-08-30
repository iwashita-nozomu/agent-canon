# Task Contract Observation

<!--
@dependency-start
contract agent-runtime
responsibility Defines task-local contract observation, terminal coverage, and durable archive routing.
upstream design runtime-log-archive.md external AgentCanon log archive ownership
upstream design ../../templates/agents/workflow_monitoring.md run-local behavior evidence
upstream design ../../eval/definitions/agent_behavior_eval.toml behavior scoring contract
downstream implementation ../../tools/runtime/lifecycle/task_contract_observation.py records and evaluates observations
downstream implementation ../../tests/agent_tools/test_task_contract_observation.py verifies schema and transition invariants
@dependency-end
-->

## Reader Map

Use this document when a task needs to answer **which contract became active,
what happened at that boundary, how the task responded, and where the evidence
was retained**.

The run-local source of truth is
`reports/agents/<run-id>/workflow_monitoring.md`. Durable retention uses the
existing `agent-canon-log` run-bundle archive. This contract does not introduce
a second telemetry repository, a synchronous network dependency, or raw prompt
collection.

## Problem and Boundary

A validation failure, tool rejection, warning, reviewer finding, or explicit
guardrail often identifies the immediate command that failed but not the
contract that became active. Retrospective prose is also difficult to aggregate
because contract identity, outcome, and resolution are not typed.

Task contract observation closes that gap with an append-only event stream. The
event records only contract identity and operational evidence:

- canonical contract identifier and source;
- task phase and activation trigger;
- open or terminal outcome;
- responsible owner;
- evidence reference and response;
- durable deferral issue, when applicable.

It must not contain user prompt text, hidden reasoning, credentials, local
absolute paths, or raw tool output. Those values remain in their existing
owner artifacts and are referenced by bounded repository-relative identifiers.

## Event Schema

Every event is a whitespace-delimited `key=value` row in
`workflow_monitoring.md` under `## Behavior Events`.

```text
contract_observation_schema=agent-canon.task-contract-observation.v1
contract_observation=observed
observation_id=contract-<20-hex>
sequence=<positive-integer>
contract_id=<canonical-contract-id>
contract_source=<repo-relative-path-or-policy-id>
phase=<phase>
trigger=<trigger>
outcome=<outcome>
owner=<role-or-owner>
evidence_ref=<bounded-evidence-reference>
response=<action-slug>
issue_ref=<owner/repo#number-when-deferred>
reason=<reason-when-not-applicable>
```

Allowed phases are:

```text
intake planning design implementation validation review closeout publication
```

Allowed triggers are:

```text
required selected guardrail warning failure rejection conflict
```

Allowed outcomes are:

```text
blocked violated satisfied deferred_with_issue not_applicable
```

`blocked` and `violated` are open outcomes. `satisfied`,
`deferred_with_issue`, and `not_applicable` are terminal outcomes.
`deferred_with_issue` requires `issue_ref`; `not_applicable` requires `reason`.

When no contract boundary became active, record exactly one explicit no-event
row instead of leaving the stream absent:

```text
contract_observation_schema=agent-canon.task-contract-observation.v1
contract_observation=none
owner=manager
reason=no-contract-triggered
```

The `none` form and `observed` form are mutually exclusive for one run.

## Identity and Append-Only State Machine

The recorder derives an observation identity when the caller omits one:

```text
observation_id =
  "contract-" +
  first20hex(
    SHA-256(
      contract_id || NUL ||
      contract_source || NUL ||
      phase || NUL ||
      trigger || NUL ||
      owner
    )
  )
```

For one `observation_id`, the identity fields are immutable and `sequence`
starts at `1`, then increases by exactly one. The accepted transitions are:

| Previous outcome | Next outcome |
| --- | --- |
| none | `blocked`, `violated`, or any terminal outcome at sequence 1 |
| `blocked` | `blocked`, `violated`, `satisfied`, `deferred_with_issue`, `not_applicable` |
| `violated` | `violated`, `satisfied`, `deferred_with_issue`, `not_applicable` |
| terminal outcome | no further transition |

An exact repeated `(observation_id, sequence, fields)` record is idempotent.
Different bytes at the same sequence are a collision. A sequence gap, identity
change, terminal rewrite, or unresolved final state fails evaluation.

Let `O(r)` be the set of observed identities in run `r`, `N(r)` the explicit
no-event count, and `terminal(o)` mean that the latest valid state of `o` is
terminal. Coverage is complete exactly when:

```text
coverage(r) =
  (N(r) = 1 and |O(r)| = 0)
  or
  (N(r) = 0 and |O(r)| > 0 and for all o in O(r): terminal(o))
```

The current-run behavior gate is green only when schema, token transport,
identity, sequence, transition, and coverage checks all pass.

## Collection Flow

Record the first open or terminal observation as soon as the contract becomes
operational. Values are token slugs; point to the owning artifact rather than
copying its content.

```bash
python3 tools/runtime/lifecycle/task_contract_observation.py \
  --report-dir reports/agents/<run-id> \
  --record \
  "contract_id=documents/runtime/runtime-log-archive.md#Branch-Policy \
contract_source=documents/runtime/runtime-log-archive.md \
phase=publication trigger=guardrail outcome=blocked owner=auditor \
evidence_ref=verification.txt#runtime-log-archive \
response=repair-publication-route"
```

The tool derives `observation_id` and `sequence`. Resolve the same observation
by repeating the immutable identity fields with a terminal outcome:

```bash
python3 tools/runtime/lifecycle/task_contract_observation.py \
  --report-dir reports/agents/<run-id> \
  --record \
  "contract_id=documents/runtime/runtime-log-archive.md#Branch-Policy \
contract_source=documents/runtime/runtime-log-archive.md \
phase=publication trigger=guardrail outcome=satisfied owner=auditor \
evidence_ref=verification.txt#runtime-log-archive \
response=archive-readback-confirmed"
```

For a run with no activated boundary:

```bash
python3 tools/runtime/lifecycle/task_contract_observation.py \
  --report-dir reports/agents/<run-id> \
  --record \
  "contract_observation=none owner=manager reason=no-contract-triggered"
```

A normal invocation evaluates the complete stream and appends a compact
behavior summary:

```text
task_contract_observation_eval_status=pass
task_contract_observation_digest=<sha256>
task_contract_observation_coverage=complete
task_contract_resolution=terminal
contract_archive_route=agent-canon-log:agent-reports
```

The built-in deterministic conformance suite is available without a run bundle:

```bash
python3 tools/runtime/lifecycle/task_contract_observation.py --self-check
```

## Eval Integration

`eval/definitions/agent_behavior_eval.toml` owns two independent checks:

1. observation coverage requires a schema-marked `observed` or `none` event and
   a passing current-run evaluator result;
2. resolution and archive routing require terminal coverage and the explicit
   `agent-canon-log:agent-reports` route.

The split prevents a run from receiving full credit merely for naming a
contract while leaving it blocked or violated. Because every failing behavior
criterion is a blocker in `evaluate_agent_run.py`, unresolved contract
observations prevent the agent evaluation from passing.

The evaluator summary is derived from the event stream. Agents must not
hand-author a `task_contract_observation_eval_status=pass` token as a substitute
for running the checker.

## Durable `agent-canon-log` Route

The local hot path has no Git or network dependency. Contract events remain in
the current run bundle while work is active. Existing archive synchronization
then publishes the complete run bundle:

```bash
python3 tools/runtime/archive/runtime_log_archive_git.py sync
python3 tools/runtime/archive/runtime_log_archive_git.py push
```

The durable location is:

```text
.agent-canon/log-archive/
  agent-reports/
    <stable-source-repository-id>/
      <run-id>/
        <snapshot-id>/
          workflow_monitoring.md
```

The source-to-snapshot mapping remains in the append-only source
`index.jsonl`. Contract observation does not invent a parallel JSONL branch or
copy the same event into source control. The existing closeout archive
readback remains the publication authority.

## Source-Free Parent Boundary

`project_template` requires tracked project files to remain readable and
validatable without a network call, parent checkout, or secret. Therefore
contract observation has two separated stages:

1. local collection and evaluation operate on the run bundle only;
2. durable synchronization is an explicit online runtime or maintainer action.

A source-free parent does not vendor AgentCanon and does not name this internal
collector. When collection is selected, the standalone AgentCanon checkout
runs it through `bootstrap.sh tool run` or the argv-only container `exec`
route. Parent project validation remains independent of that runtime.

Offline validation must not claim archive publication. It may report the local
evaluation status and retain the run bundle until the mounted archive becomes
available. A successful archive claim still requires the normal sync, push,
and remote-ref readback evidence.

## Failure Handling

- `coverage_missing`: record an observation or the explicit `none` form.
- `identity_collision`: use a new identity for a genuinely different contract;
  do not rewrite the prior record.
- `sequence_gap` or `sequence_collision`: recover from the latest accepted
  sequence and append a new record.
- `transition_invalid`: preserve the terminal record and open a new observation
  for a different operational boundary.
- `unresolved_observation`: repair the contract outcome or use
  `deferred_with_issue` with a durable issue reference.
- archive synchronization failure: keep the local run bundle and archive spool;
  do not claim `agent-canon-log` publication until readback succeeds.
