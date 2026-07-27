# W2 F1-F6 Repair Design v2

## Reader Map

- Purpose: resolve the owner-level D1-D5 escalation against the `996b90d`
  design while preserving F1-F6 intent and the F5 public-negative-test
  contract.
- Audience: canonical owner editors, the W2 implementation writer, independent
  design and implementation reviewers, and the W3/parent integration consumer.
- Reader order: Request Clauses → Owner Surfaces → Selected Architecture →
  Rejected Alternatives → Abstract Design Frame → Implementation Source Packet
  → Design Side-Effect Map → Design-to-Implementation Trace → Exact Acceptance
  Predicates.
- Artifact relation: this file is an append-only successor to
  `w2_f1_f6_repair_design.md`. It supersedes that artifact for future W2
  implementation authority but does not rewrite or erase the v1 review record.
- First artifact: the Selected Architecture section. It answers which one
  canonical ledger record supplies every CompletionCoverage recomputation
  input without creating a second state machine.
- Structure contract:
  - `structure_kind=document`
  - `document_unit=run-local detailed-design successor`
  - `document_split_decision=split:owner-level escalation resolution requires an independently reviewable successor while v1 remains historical evidence`
  - `structure_visual_plan=text-only:exact schemas, signatures, predicates, and artifact tables are more precise than a rendered process diagram`
  - `structure_source_map=review artifact and canonical owner sections to D1-D5 sections below`
  - `structure_oop_contract=one replaceable completion-authority responsibility unit`
  - `discourse_relations=not_required`
  - `prose_graph_execution=not_run_by_user_constraint`
  - `structure_invalid_interpretations_recorded=yes`
- Dependency classification: this is a run-local report under `reports/`,
  which the dependency-header scanner excludes. It therefore carries no
  durable dependency-manifest edges. The Implementation Source Packet records
  read dependencies in prose, and durable canon files must not add upstream or
  downstream dependency edges to this run-local artifact.
- Invalid interpretations:
  - this artifact is not implementation approval;
  - a stale ordered interface is evidence, not schema or state authority;
  - a stored success boolean is never completion authority;
  - this artifact does not contain or require its own commit, tree, blob, or
    SHA256 identity.

## Request Clauses

- `D1-CANONICAL-AUTHORITY`: define the sole-authority ledger event schema,
  semantic kind, writer owner, logical key, revision/supersession ordering,
  unique selection, typed missing/duplicate failures, and exact public resolver
  signatures for active clauses, owner contract, source binding, schedule,
  open-work, repair, crossing-edge, and topology state.
- `D2-BRANCH-REASON`: converge every exact W2 branch-reason consumer on
  `convergence_w2_gate_completion_authority`, owned by
  `agents/canonical/CODEX_WORKFLOW.md`; reject the stale interface value as
  authority.
- `D3-GROUP-EQUALITY`: preserve per-member source-event correspondence and then
  require exact cross-member equality for owner, state owner, API owner,
  dependency owner, responsibility unit, outcome, and approved evidence.
- `D4-OWNER-AND-DEPENDENCY-CLOSURE`: make
  `agents/COMMUNICATION_PROTOCOL.md` and
  `agents/canonical/CODEX_WORKFLOW.md` real implementation surfaces; enumerate
  selected templates, closeout projections, tests, dependency headers, and
  reverse edges; prohibit durable canon from depending on run-local reports.
- `D5-NON-SELF-REFERENTIAL-PUBLICATION`: define the complete acyclic chain from
  design approval through source freeze, external independent implementation
  review, decision binding, and integration consumption.
- `W2-F1` through `W2-F6`: retain the approved repair intent from v1, with D1-D5
  replacing its underspecified owner-level decisions.
- `W2-F5`: retain public typed negative tests and honest
  `pending`/`deferred_by_user` validation states; no hand-written pass artifact.
- `DESIGN-ONLY-V2`: edit no implementation, source, test, hook, template,
  canonical owner, or interface path in this commit.

## Owner Surfaces

| Surface | Canonical responsibility | v2 decision |
| --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` `CompletionCoverage v1 Schema Contract` | CompletionCoverage event/schema and group semantics | Owns the new `completion_authority` event payload, per-member correspondence, and cross-member equality rule. |
| `agents/canonical/CODEX_WORKFLOW.md` `CompletionCoverage Applicability And State Contract` | Applicability, transition order, topology state, W2 branch reason | Owns the single branch-reason value and the allowed state-transition graph. |
| `documents/design/dependency-manifest-design.md` `Bidirectional Consistency` | Durable dependency edges and reverse-edge matching | Owns the header closure enumerated in the Side-Effect Map. |
| `documents/conventions/REVIEW_PROCESS.md` | Review artifact lifecycle and merge evidence | Owns external review identity, decision refresh, and latest-source review rules. |
| `tools/agent_tools/work_log.py` | Append-only ledger, snapshot, authority resolution | Owns event validation, deterministic snapshot identity, and unique authority-head selection. |
| `tools/agent_tools/workflow_monitor.py` | Public semantic-event append surface | Preserves the dedicated `completion_authority` object without flattening or synthesizing success. |
| `tools/agent_tools/report_artifact_checks.py` | Projection, typed checks, boundary derivation, artifact identity checks | Removes caller-owned completion inputs and recomputes only from the ledger snapshot. |
| `tools/agent_tools/task_close.py` | Public closeout consumer | Keeps `completion_coverage_consumer(report_dir)` and consumes resolver/check results rather than stored success. |
| `tools/agent_tools/waterfall_gate_check.py` | Design-review target identity gate | Validates the design approval artifact against exact path/commit/tree/blob/SHA fields. |
| Run-local reports and ordered interface | Evidence and handoff only | Never override canonical owner docs or the selected ledger authority event. |

## Selected Architecture

### Decision

Select one full-snapshot canonical aggregate state event. The existing
`publication_state` semantic kind carries a dedicated top-level
`completion_authority` object with schema
`agent-canon.completion-authority.v1`. Every successor event contains the full
authority snapshot; no resolver merges partial authority state from different
revisions.

This event and the ordinary clause/evidence events together form the single
append-only ledger `L`. CompletionCoverage remains the pure projection
`P = f(L)`. The aggregate event is not a second ledger and does not store
`ok`, G1-G5 results, `all_planned_chunks_complete`, or
`overall_delivery_complete`.

### Canonical event envelope

The event envelope is exact:

```json
{
  "run_id": "<report directory name>",
  "context_id": "<canonical context id>",
  "event_id": "completion-authority:<context_id>:<revision>",
  "semantic_kind": "publication_state",
  "owner": "<source_binding.component_manager>",
  "state_owner": "<source_binding.component_manager>",
  "api_owner": "<owner_contract.api_owner>",
  "dependency_owner": "<owner_contract.dependency_owner>",
  "responsibility_unit": "completion_authority",
  "intent_id": "W2-completion-authority",
  "outcome": "<completion_authority.transition_state>",
  "evidence_refs": ["<non-empty source references>"],
  "artifact_refs": ["<non-empty run artifact references>"],
  "source_binding": {
    "run_id": "<run_id>",
    "context_id": "<context_id>"
  },
  "completion_authority": {}
}
```

Required event rules:

1. `semantic_kind` is the existing non-groupable `publication_state`.
2. `clause_id`, `mapping_mode=group`, `group_identity`, and
   `member_clause_ids` are forbidden on the authority event.
3. The component manager named by the payload source binding is the sole writer
   owner. A worker or reviewer may produce evidence, but the parent/component
   manager appends the next aggregate authority revision after verifying that
   evidence.
4. `owner` and `state_owner` equal `source_binding.component_manager`.
5. `outcome` equals `completion_authority.transition_state`.
6. Every event that participates in CompletionCoverage by carrying
   `clause_id`, `gate_evidence`, `failure_response`, `resource_certificate`,
   `monitor_evidence`, or `completion_authority` must carry the minimal
   `{run_id, context_id}` `source_binding`, and it must match the selected
   authority event.

### `completion_authority` payload schema

Every revision carries every field below:

```json
{
  "schema": "agent-canon.completion-authority.v1",
  "logical_key": {
    "run_id": "<run_id>",
    "context_id": "<context_id>",
    "authority": "completion_authority"
  },
  "revision": 1,
  "supersedes_event_id": null,
  "transition_state": "context_bound",
  "repair_return_state": null,
  "source_binding": {
    "run_id": "<run_id>",
    "context_id": "<context_id>",
    "organizer_context_id": "<organizer context>",
    "parent": "<parent owner>",
    "component_manager": "<component manager>",
    "assigned_unit": "<replaceable unit>",
    "source_binding": {
      "run_id": "<run_id>",
      "context_id": "<context_id>"
    },
    "source_refs": ["<non-empty source refs>"]
  },
  "active_clause_ids": ["<ordered unique clause ids>"],
  "owner_contract": {
    "owner": "<owner>",
    "state_owner": "<state owner>",
    "api_owner": "<API owner>",
    "dependency_owner": "<dependency owner>"
  },
  "schedule_state": {
    "w2_implementation_complete": false,
    "w2_review_complete": false,
    "source_freeze_review_complete": false,
    "formatter_and_static_checks_pass": false
  },
  "open_work_state": {
    "planned_work_complete": false
  },
  "repair_state": {
    "open_repairs": []
  },
  "crossing_edge_state": {
    "open_crossing_edges": []
  },
  "topology": {
    "run_id": "<run_id>",
    "context_id": "<context_id>",
    "observation_ref": "<evidence ref>",
    "global_publication_state": "context_bound",
    "routing_gate": "pending",
    "writer_release_order_complete": false,
    "final_review_approved": false,
    "closeout_unlocked": false,
    "branch_creation_reason": "convergence_w2_gate_completion_authority",
    "source_freeze_before_review": false,
    "formatter_static_events": [],
    "writer_cardinality": 1,
    "writer_collision_state": "collision_preserved",
    "descendant_disposition": {
      "status": "<status>",
      "release": "<release>",
      "retained": "<retained>"
    },
    "topology_schema": "agent-canon.control-topology.v1",
    "topology_order": [
      "design_approved",
      "writer_released",
      "source_frozen",
      "change_review_approved"
    ]
  }
}
```

Payload predicates:

- `active_clause_ids` is non-empty, ordered as the active rows appear in
  `user_request_contract.md`, and duplicate-free. The aggregate event is the
  runtime authority; the user contract remains its cited source evidence.
- `owner_contract` has exactly the four existing owner fields.
- `source_binding` keeps the existing full binding shape. Its nested binding,
  event envelope, logical key, and every participating event must agree on
  `run_id` and `context_id`.
- All schedule/open-work fields are exact booleans.
- `open_repairs` and `open_crossing_edges` are exact typed lists. Empty lists
  mean none; missing lists are errors.
- The topology carries every existing required field. No non-empty-string or
  truthiness fallback is permitted.
- `branch_creation_reason` has exactly one allowed value:
  `convergence_w2_gate_completion_authority`.
- `global_publication_state` equals `transition_state`.
- `routing_gate` is `pending` before `publication_ready` and is `verified` only
  for `publication_ready` and `delivered`.
- `writer_release_order_complete` is true from `writer_released` onward.
- `source_freeze_before_review` is true from `source_frozen` onward and must be
  true before `change_review_pending`.
- `final_review_approved` is true from `change_review_approved` onward.
- `closeout_unlocked` is true only for `publication_ready` and `delivered`.
- `writer_cardinality` is exactly `1`;
  `writer_collision_state` is exactly `collision_preserved`;
  `topology_order` is the exact four-item list shown above.

### Ordering, supersession, and transition selection

The logical key is the exact object
`{run_id, context_id, authority: completion_authority}`.

Selection algorithm:

1. Read all ledger events without accepting a caller-supplied snapshot label.
2. Derive `snapshot_digest` from the canonical sorted event bytes and set
   `snapshot_identity` to `sha256:<snapshot_digest>`.
3. Select events with `semantic_kind=publication_state`,
   `responsibility_unit=completion_authority`, and the exact payload schema.
4. Require exactly one logical key for the report `run_id`. More than one
   context/logical key is fail-closed.
5. Require revision `1` exactly once with `supersedes_event_id=null`.
6. For every revision `n > 1`, require exactly one event, revision `n - 1`,
   and `supersedes_event_id` equal to the exact event ID for revision `n - 1`.
7. Require the event ID to equal
   `completion-authority:<context_id>:<revision>`.
8. Require one unsuperseded head and no revision gap, fork, or orphan
   supersession reference.
9. Validate each state transition against the
   `CODEX_WORKFLOW.md` sequence:
   `context_bound` → `design_pending` → `design_approved` →
   `writer_release_pending` → `writer_released` →
   `source_freeze_pending` → `source_frozen` →
   `change_review_pending` → `change_review_approved` →
   `integration_pending` → `publication_ready` → `delivered`.
10. A failure may transition to `repair_pending`. That event must set
    `repair_return_state` to the exact owning pre-failure state. Its successor
    is either that exact state or `escalation_pending`.
    `escalation_pending` cannot produce a ready result.
11. Return the unique valid head as the completion authority. Do not merge
    fields from superseded revisions.

Typed resolver errors are stable strings:

- `completion_authority:missing`
- `completion_authority:multiple_logical_keys`
- `completion_authority:schema_invalid:<field>`
- `completion_authority:duplicate_revision:<revision>`
- `completion_authority:revision_one_missing`
- `completion_authority:revision_gap:<previous>:<next>`
- `completion_authority:event_id_mismatch:<revision>`
- `completion_authority:supersedes_missing:<event_id>`
- `completion_authority:supersedes_mismatch:<revision>`
- `completion_authority:multiple_heads`
- `completion_authority:invalid_transition:<from>:<to>`
- `completion_authority:repair_return_state_invalid`
- `completion_authority:source_binding_mismatch:<event_id>`
- `completion_authority:writer_owner_mismatch:<event_id>`
- `completion_authority:branch_creation_reason_mismatch`

### Exact public resolver and consumer signatures

The implementation must use these signatures:

```python
def read_ledger_snapshot(report_dir: Path) -> dict[str, object]:
    ...

def resolve_completion_authority(
    ledger_snapshot: Mapping[str, object],
) -> dict[str, object]:
    ...
```

`resolve_completion_authority` returns:

```json
{
  "schema": "agent-canon.completion-authority-resolution.v1",
  "ok": true,
  "selected_event_id": "<event id>",
  "selected_revision": 1,
  "logical_key": {},
  "authority": {},
  "errors": []
}
```

No caller supplies `active_clause_ids`, `owner_contract`, `source_binding`,
schedule/open-work/repair/crossing-edge state, topology, snapshot identity, or
monitor evidence to the projection/check boundary.

```python
def materialize_completion_coverage_from_work_log(
    report_dir: Path,
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> Path:
    ...

def project_completion_coverage(
    ledger_snapshot: Mapping[str, object],
    schema_version: str = COMPLETION_COVERAGE_SCHEMA,
) -> dict[str, object]:
    ...

def check_completion_coverage(
    completion_coverage: Mapping[str, object],
    ledger_snapshot: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> dict[str, object]:
    ...

def evaluate_completion_boundary(
    coverage_check: Mapping[str, object],
    ledger_snapshot: Mapping[str, object],
) -> dict[str, object]:
    ...

def write_completion_coverage_artifact(
    report_dir: Path,
    ledger_snapshot: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> Path:
    ...

def generated_completion_coverage_errors(
    report_dir: Path,
    artifact: Mapping[str, object],
) -> list[str]:
    ...

def completion_coverage_consumer(report_dir: Path) -> dict[str, object]:
    ...
```

The last two public signatures remain source-compatible. Both reconstruct the
ledger snapshot and resolution internally. Projection metadata adds
`completion_authority_event_id`, `completion_authority_revision`, and
`completion_authority_logical_key`; those fields and the derived
`snapshot_identity`/digest fingerprint every stored view.

### D2 branch-reason convergence

The canonical value is
`convergence_w2_gate_completion_authority`. The stale ordered interface value
`convergence_w2_writer_owned_after_git_index_blocker` is a negative fixture,
not authority.

Every exact consumer is:

| Consumer | Required change |
| --- | --- |
| `agents/canonical/CODEX_WORKFLOW.md` | Retain the single owner value and state that all projections must match it. |
| `agents/COMMUNICATION_PROTOCOL.md` | Add the exact value to the authority/topology schema. |
| `tools/agent_tools/report_artifact_checks.py` | Change `BRANCH_CREATION_REASON` and reject any other value. |
| `work_log.py` authority resolver | Validate the aggregate topology value before selecting a head. |
| `workflow_monitor.py` | Preserve the value inside the structured authority payload. |
| `task_close.py` | Consume the resolver result and expose the typed mismatch reason. |
| `completion_authority.topology` | Store only the canonical value. |
| `ordered_integration_interface.json` v2 | Use the canonical value at top level and in topology. |
| `tests/agent_tools/test_task_start_and_close.py` | Replace the stale positive fixture and add the stale value as a public negative case. |
| `tests/agent_tools/test_work_log.py` | Test resolver rejection of a stale value. |

Generic branch-guard markers such as `branch_creation_reason=<reason>` remain
unchanged because they validate authority presence, not this W2-specific value.

### D3 group correspondence and cross-member equality

Group validation has two mandatory phases.

Phase 1, member-to-event correspondence:

1. Every member clause has one distinct canonical source event.
2. The row `source_event_ref` resolves to that event.
3. The row and event match exactly on `clause_id`, `group_identity`,
   `member_clause_ids`, `mapping_mode`, semantic kind, owner, state owner,
   API owner, dependency owner, responsibility unit, outcome, and
   `evidence_refs`.
4. Missing or duplicate member events fail before cross-member comparison.

Phase 2, cross-member equality:

1. Sort resolved member events by `clause_id`; the first is the deterministic
   comparison baseline.
2. Compare every other canonical member event with the baseline.
3. Require exact equality for:
   `owner`, `state_owner`, `api_owner`, `dependency_owner`,
   `responsibility_unit`, `outcome`, and `evidence_refs`.
4. The approved evidence rule is exact ordered-list equality. Each list must be
   non-empty and duplicate-free; set equality or group-shared fallback is not
   sufficient.
5. The equality check uses resolved source events, never coverage rows or a
   group-level copied facts tuple.

Typed group errors are:

- `group_member:missing:<group_identity>:<clause_id>`
- `group_member:duplicate:<group_identity>:<clause_id>`
- `group_member:source_event_mismatch:<group_identity>:<clause_id>:<field>`
- `group_member:member_set_mismatch:<group_identity>:<clause_id>`
- `group_member:cross_equality_mismatch:<group_identity>:<field>:<baseline_clause>:<member_clause>`
- `group_member:evidence_not_unique:<group_identity>:<clause_id>`

The existing non-groupable semantic-kind prohibition remains unchanged.

### D5 complete non-self-referential publication DAG

The selected path uses a decision-binding commit. The commit identity is an
external input to the integration consumer and is never written inside the
interface committed by that same commit.

| Node | Owner | Path or Git object | Required fields and identity |
| --- | --- | --- | --- |
| `D` design successor | `detailed_designer` | this v2 path in a design-only commit | External readback records design commit/tree and file blob/SHA256. This file records none of those self identities. |
| `DR` independent design approval | `detailed_design_reviewer` | `reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_<D-short>.md` | `design_path`, `design_commit`, `design_tree`, `design_blob`, `design_sha256`, `decision=APPROVE`, reviewer separation. It does not contain its own SHA/blob. |
| `S` source freeze | W2 implementation writer | Git commit/tree descending from `D` | `source_commit`, `source_tree`, base commit/tree, source diff SHA256, exact changed paths. The stale interface is not authority in `S`. |
| `IR` independent implementation review | `change_reviewer`, separate from writer | `reports/agents/convergence-w2-gates-completion-20260716/w2_implementation_review_<S-short>.md` | `reviewed_source_commit`, `reviewed_source_tree`, `reviewed_diff_sha256`, `decision=APPROVE`, findings disposition. It does not contain its own SHA/blob. |
| `B` decision-binding commit | parent/integrator | commit descending directly from `S`, updating the ordered interface | Interface records `D`, external readback of `DR`, `S`, and external readback of `IR`. The interface does not contain `B`, its own tree, its own blob, or its own SHA256. |
| `CR` external closeout receipt | verifier/auditor | run-local `closeout_gate.md` after `B` exists | Records externally supplied `B`, `B` tree, interface path/blob/SHA256, and integration-consumer result. It does not hash its own bytes. |
| Integration consumer | `task_close` verifier | current checkout plus externally supplied `B=HEAD` | Verifies the entire chain and unlocks only when every prior identity and decision matches. |

The ordered interface becomes
`agent-canon.ordered-integration-interface.v2` with these exact top-level
objects:

```json
{
  "schema": "agent-canon.ordered-integration-interface.v2",
  "run_id": "convergence-w2-gates-completion-20260716",
  "branch_creation_reason": "convergence_w2_gate_completion_authority",
  "design_binding": {
    "path": "<D path>",
    "commit": "<D>",
    "tree": "<D tree>",
    "blob": "<D blob>",
    "sha256": "<D SHA256>",
    "review_path": "<DR path>",
    "review_sha256": "<DR SHA256>",
    "review_blob": "<DR blob>",
    "review_decision": "APPROVE"
  },
  "source_freeze": {
    "base_commit": "80e63c4134058204e243c6140522d9e3671f9de6",
    "base_tree": "5174b0dc1426e6afe8db78ba5f43a2320e79feef",
    "commit": "<S>",
    "tree": "<S tree>",
    "diff_sha256": "<source diff SHA256>",
    "changed_paths": [],
    "source_freeze_before_review": true
  },
  "implementation_review": {
    "path": "<IR path>",
    "sha256": "<IR SHA256>",
    "blob": "<IR blob>",
    "decision": "APPROVE",
    "reviewed_source_commit": "<S>",
    "reviewed_source_tree": "<S tree>",
    "reviewed_diff_sha256": "<source diff SHA256>"
  },
  "decision": {
    "state": "change_review_approved",
    "integration_ready": true,
    "decision_source": "implementation_review"
  },
  "topology": {}
}
```

The interface `topology` exactly matches the selected completion-authority
event at `change_review_approved`, including the canonical branch reason,
source freeze, order, identities, and booleans. It may not introduce a
different state machine.

The exact integration verifier signature is:

```python
def ordered_integration_decision_consumer(
    workspace: Path,
    report_dir: Path,
    decision_binding_commit: str,
) -> dict[str, object]:
    ...
```

`report_artifact_checks.py` implements this verifier, and `task_close.py`
imports it and calls it with the externally observed current `HEAD`. The
verifier:

1. reads the ordered interface from `decision_binding_commit`;
2. requires `decision_binding_commit` to descend from `source_freeze.commit`;
3. resolves and hashes `D`, `DR`, `S`, and `IR`;
4. verifies each review artifact binds the preceding tuple and says
   `APPROVE`;
5. rejects any interface field that claims the interface's own containing
   commit/tree/blob/SHA;
6. compares interface topology and branch reason with the selected authority
   event; and
7. returns ready only when the decision state is
   `change_review_approved` and all identity checks pass.

Typed publication failures include:

- `ordered_integration:decision_commit_missing`
- `ordered_integration:source_not_ancestor`
- `ordered_integration:design_identity_mismatch`
- `ordered_integration:design_review_missing`
- `ordered_integration:design_review_identity_mismatch`
- `ordered_integration:design_review_not_approved`
- `ordered_integration:source_identity_mismatch`
- `ordered_integration:implementation_review_missing`
- `ordered_integration:implementation_review_identity_mismatch`
- `ordered_integration:implementation_review_not_approved`
- `ordered_integration:interface_self_identity_forbidden`
- `ordered_integration:branch_creation_reason_mismatch`
- `ordered_integration:topology_mismatch`

## Rejected Alternatives

The choice uses hard constraints only; no weighted score is used.

| Alternative | Ledger sole authority | Atomic coherent state | Unique deterministic head | Existing semantic kinds | No second state machine | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Fine-grained typed authority events for clauses, owner, schedule, repair, edges, and topology | Pass | Fail: a resolver can combine fields from different revisions unless it invents a transaction/batch layer | Fail without another grouping protocol | Pass | Fail if a batch coordinator is added | Rejected |
| One full-snapshot `completion_authority` aggregate event on `publication_state` | Pass | Pass: each revision is a complete state | Pass through revision/supersession chain | Pass | Pass | Selected |
| External canonical state JSON referenced by a ledger pointer event | Fail: the file becomes another authority | Pass | Pass | Pass | Fail: second persistence/state surface | Rejected |

The fine-grained option could only satisfy atomicity by adding a batch identity,
commit marker, and batch resolver. That is the aggregate design under another
name with more failure modes, so it is not an alternate implementation route.

## Abstract Design Frame

### Replaceable responsibility unit

D1-D5 form one replaceable **completion-authority responsibility unit**:

1. append and resolve one canonical authority head from the run ledger;
2. project CompletionCoverage from that ledger only;
3. validate per-member and cross-member group facts;
4. enforce canonical topology and branch-reason state;
5. bind design, source, review, and integration decisions through an acyclic
   identity chain; and
6. expose one closeout/integration consumer result.

Replacing one module without preserving this full contract is not a valid
slice. The unit can be replaced only by another implementation that preserves
the event schema, transition graph, exact signatures, typed errors, group
predicates, publication DAG, and public negative-test oracles.

### Authority flow

1. `work_log.py` reconstructs `L` and resolves one authority head.
2. `report_artifact_checks.py` computes `P = f(L)`, coverage checks, completion
   boundary, and identity checks.
3. `task_close.py` consumes recomputed results and never trusts stored success.
4. `workflow_monitor.py` is an append adapter, not an authority or second state
   machine.
5. Canonical docs own schema/state; templates and skills are projections.
6. Run-local interface/review files carry evidence but cannot override owner
   docs or the selected authority event.

### Invariants

- Every recomputation input comes from one selected aggregate revision.
- Every stored view is fingerprint-bound to the derived ledger snapshot and
  authority event.
- Missing, duplicate, forked, stale, or binding-mismatched authority events
  fail closed.
- Group validity requires both per-member correspondence and exact
  cross-member equality.
- The W2 branch reason has one canonical value.
- Design/source/review/decision artifacts form a DAG; no artifact hashes its
  own bytes or names its own containing Git identity.
- F5 evidence remains pending until owning tools actually run.

### Non-goals

- No new database, external state service, compatibility wrapper, runner,
  scheduler, worktree, alternate closeout route, or second completion schema.
- No source/test/owner-doc/template/interface edit in this v2 design commit.
- No change to failure taxonomy ownership, W1 resource production, GPU
  semantics, unrelated OOP score surfaces, or the canonical docs checker.

## Implementation Source Packet

### Bound predecessor and review identities

- Source predecessor commit:
  `80e63c4134058204e243c6140522d9e3671f9de6`
- Source predecessor tree:
  `5174b0dc1426e6afe8db78ba5f43a2320e79feef`
- v1 design commit:
  `996b90d2915e9eab7cd384ab6d1b1b45bb6ae179`
- v1 design tree:
  `8aed6c28e2f009c0378f403c32c03723792e9a67`
- v1 design path:
  `reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design.md`
- v1 design blob:
  `542296bf07a3efc2b6edc410a69079aa5c175cdc`
- v1 design SHA256:
  `497733373c42927f12cda9fc10fcd2c677f030977494ce13b6974029a13eb5a9`
- Owner-level recheck artifact:
  `/mnt/l/workspace/agent-canon-convergence-w2-final-writer-owned/reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_996b90d.md`
- Recheck SHA256:
  `f5cc1b9ce6224c7efdb05bcfde0276db680b660cb3d7b94acd04fdc4e0d933fa`
- Recheck blob:
  `ca90caecf9233001e816e541557090afde08ad07`
- Stale ordered-interface blob:
  `0d72364dc37db1d0241d40444dbca15ea4cb95ec`
- Stale ordered-interface SHA256:
  `40aa042eb2222f7576613edaf3c93eed7088f3461ec87e3d5d3b93fa0c502aa8`

This v2 artifact intentionally contains no identity for the commit/tree/blob/
SHA that will contain this file. Those values are returned only by external
readback after commit.

### Mandatory read-before-edit order

1. This v2 artifact in full.
2. The D1-D5 recheck artifact and the v1 design above.
3. `agents/COMMUNICATION_PROTOCOL.md` `CompletionCoverage v1 Schema Contract`.
4. `agents/canonical/CODEX_WORKFLOW.md`
   `CompletionCoverage Applicability And State Contract`.
5. `documents/design/dependency-manifest-design.md` `Bidirectional Consistency`,
   `Isolated Manifests`, and cycle rules.
6. `documents/conventions/REVIEW_PROCESS.md` review artifact, post-fix rerun, merge, and
   evidence sections.
7. `tools/agent_tools/work_log.py` event validation, append, snapshot, digest.
8. `tools/agent_tools/workflow_monitor.py` semantic event parser and append
   boundary.
9. `tools/agent_tools/report_artifact_checks.py` completion constants,
   projection, mapping/group checks, artifact writer, boundary, consumer
   helper.
10. `tools/agent_tools/task_close.py` completion consumer and closeout
    integration.
11. `tools/agent_tools/waterfall_gate_check.py` design artifact identity gate.
12. Every template, projection, header, interface, and test named in the
    Side-Effect Map.

### Implementation boundary

The implementation starts only after an independent reviewer returns
`APPROVE` for this exact v2 artifact. The implementation source freeze contains
canonical docs, templates/projections, code, headers, and tests. The ordered
interface update is excluded from that source-freeze commit and occurs only in
the later decision-binding commit.

## Design Side-Effect Map

| Path | Exact future change | Owner/review gate | Clauses |
| --- | --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Define `completion_authority.v1`, participating-event binding, aggregate selection contract, two-phase group predicate, typed errors, and review identity packet fields. | Schema owner; detailed-design and document-flow review. | D1, D3, D4, D5 |
| `agents/canonical/CODEX_WORKFLOW.md` | Replace split non-routing inputs with the selected authority event, retain the transition graph, define topology-state predicates, and declare the sole branch reason. | State owner; detailed-design and workflow review. | D1, D2, D4, D5 |
| `documents/conventions/REVIEW_PROCESS.md` | Require design and implementation review artifacts to bind exact prior tuples; prohibit self-byte hashes; require refreshed review on changed tuples. | Review-policy owner. | D4, D5 |
| `agents/skills/codex-task-workflow.md` | Project the aggregate authority event/resolver and decision-binding consumer without restating schema. | Skill projection review. | D1, D4, D5 |
| `agents/skills/report-writing.md` | Report selected authority event/revision and recomputed gates; never report stored values as authority. | Report projection review. | D1, D4 |
| `agents/workflows/implementation-waterfall-workflow.md` | Gate implementation on v2 design approval, source freeze before external review, and decision binding before integration. | Workflow review. | D4, D5 |
| `agents/agents_config.json` | Update auditor/verifier notes to require authority resolution and decision-binding verification. | Runtime alignment review. | D4, D5 |
| `agents/templates/work_log.md` | Add the canonical Ledger Events section and aggregate-authority append guidance. | Template review. | D1, D4 |
| `agents/templates/workflow_monitoring.md` | Document structured `completion_authority` passthrough and prohibit synthesized success. | Template/runtime review. | D1, D4 |
| `agents/templates/schedule.md` | Keep TODO evidence while stating that the selected aggregate event is runtime completion authority. | Template/workflow review. | D1, D4 |
| `agents/templates/closeout_gate.md` | Add authority event/revision/logical key/digest and external decision-binding commit/interface/review identity receipt fields. | Closeout template review. | D1, D4, D5 |
| `agents/templates/design_review.md` | Add exact design path/commit/tree/blob/SHA and reviewer-separation fields; no review self hash. | Design-review template owner. | D4, D5 |
| `agents/templates/change_review.md` | Add exact source commit/tree/diff SHA fields and reviewer separation; no review self hash. | Change-review template owner. | D4, D5 |
| `agents/templates/final_review.md` | Verify the complete D→DR→S→IR→B chain and latest tuple. | Final-review template owner. | D4, D5 |
| `tools/agent_tools/work_log.py` | Add dedicated payload validation, derive snapshot identity, and implement `resolve_completion_authority`. | Code review and targeted tests. | D1, D2 |
| `tools/agent_tools/workflow_monitor.py` | Add `completion_authority` to structured passthrough and preserve exact payload/`group_identity`. | Runtime code review. | D1, D3 |
| `tools/agent_tools/report_artifact_checks.py` | Remove caller authority inputs, change signatures, recompute all views from ledger, enforce D2/D3 predicates, and verify the publication chain. | Code review and public typed tests. | D1, D2, D3, D5, F1-F5 |
| `tools/agent_tools/task_close.py` | Keep public consumer signature, consume resolver and ordered-integration result, expose typed failures. | Closeout code review. | D1, D2, D5, F1-F5 |
| `tools/agent_tools/waterfall_gate_check.py` | Validate exact design approval tuple and reject stale review targets. | Design-gate code review. | D5 |
| `reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json` | In decision-binding commit only, replace stale v1 identity with v2 schema and prior-node hashes; never self-bind. | Parent/integrator plus independent artifact review. | D2, D5 |
| `tests/agent_tools/test_work_log.py` | Authority schema, unique head, revision, supersession, transition, source binding, writer owner, branch reason negatives. | Public ledger boundary test review. | D1, D2, F5 |
| `tests/agent_tools/test_workflow_monitor.py` | Structured authority and group-identity round trip without synthesized success. | Public monitor boundary test review. | D1, D3, F5 |
| `tests/agent_tools/test_task_start_and_close.py` | Generated positive fixture and all public negative closeout cases, including stale branch reason and publication chain. | Public closeout test review. | D1-D3, D5, F1-F5 |
| `tests/agent_tools/test_waterfall_gate_check.py` | Missing/mismatched design tuple and stale approval negatives. | Design-gate test review. | D5 |
| `tests/agent_tools/test_agent_team_templates.py` | Assert new template identity and authority fields render. | Template test review. | D4, D5 |

### Durable dependency-header and reverse-edge closure

The run-local v1/v2/review artifacts receive no durable graph edges. The source
implementation must add or normalize these durable pairs:

| Canonical side | Required downstream edge | Consumer reverse edge |
| --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | `tools/agent_tools/work_log.py` | `work_log.py` adds `upstream design ../../agents/COMMUNICATION_PROTOCOL.md`. |
| `agents/COMMUNICATION_PROTOCOL.md` | `tools/agent_tools/workflow_monitor.py` | `workflow_monitor.py` adds the same canonical upstream. |
| `agents/COMMUNICATION_PROTOCOL.md` | `tools/agent_tools/report_artifact_checks.py` | `report_artifact_checks.py` adds the same canonical upstream. |
| `agents/COMMUNICATION_PROTOCOL.md` | `tools/agent_tools/task_close.py` | `task_close.py` adds the same canonical upstream. |
| `agents/COMMUNICATION_PROTOCOL.md` | `documents/conventions/REVIEW_PROCESS.md` | `REVIEW_PROCESS.md` adds `upstream design ../agents/COMMUNICATION_PROTOCOL.md`. |
| `agents/COMMUNICATION_PROTOCOL.md` | `agents/templates/work_log.md`, `workflow_monitoring.md`, `closeout_gate.md`, `design_review.md`, `change_review.md`, `final_review.md` | Each template adds `upstream design ../COMMUNICATION_PROTOCOL.md`. |
| `agents/COMMUNICATION_PROTOCOL.md` | `agents/workflows/implementation-waterfall-workflow.md`, `agents/skills/report-writing.md` | Each projection adds the matching canonical upstream. |
| `agents/canonical/CODEX_WORKFLOW.md` | `tools/agent_tools/work_log.py`, `workflow_monitor.py`, `report_artifact_checks.py`, `task_close.py` | Each code header adds or retains `upstream design ../../agents/canonical/CODEX_WORKFLOW.md`. |
| `agents/canonical/CODEX_WORKFLOW.md` | `agents/templates/work_log.md`, `workflow_monitoring.md`, `schedule.md`, `closeout_gate.md` | Each template adds or retains `upstream design ../canonical/CODEX_WORKFLOW.md`. |
| `agents/canonical/CODEX_WORKFLOW.md` | `agents/skills/codex-task-workflow.md`, `agents/skills/report-writing.md`, `agents/workflows/implementation-waterfall-workflow.md` | Each projection adds or retains the matching canonical upstream. |
| `agents/canonical/CODEX_WORKFLOW.md` | `documents/conventions/REVIEW_PROCESS.md`, `agents/agents_config.json` | The document and JSON manifest add the matching canonical upstream. |
| `tools/agent_tools/work_log.py` | `workflow_monitor.py`, `report_artifact_checks.py`, `test_work_log.py`, `test_task_start_and_close.py` | Each consumer has one matching `upstream implementation` edge; duplicate current work-log/monitor edges are normalized to one pair. |
| `tools/agent_tools/report_artifact_checks.py` | `task_close.py`, `test_task_start_and_close.py` | Both consumers carry matching `upstream implementation` edges. |
| `tools/agent_tools/task_close.py` | `test_task_start_and_close.py` | The test retains/adds the matching reverse edge. |
| `tools/agent_tools/workflow_monitor.py` | `test_workflow_monitor.py` | Existing pair remains exact. |
| `tools/agent_tools/waterfall_gate_check.py` | `test_waterfall_gate_check.py` | Existing/new pair is made bidirectional. |
| `agents/templates/work_log.md` | `tools/agent_tools/waterfall_gate_check.py`, `tools/agent_tools/task_close.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_agent_team_templates.py` | Each consumer adds the exact template as `upstream design`; the template adds each selected consumer as `downstream implementation`. |
| `agents/templates/workflow_monitoring.md` | `tools/agent_tools/workflow_monitor.py`, `tools/agent_tools/task_close.py`, `tests/agent_tools/test_workflow_monitor.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_agent_team_templates.py` | Each consumer adds or retains the exact template upstream; the template lists each selected consumer downstream. |
| `agents/templates/schedule.md` | `tools/agent_tools/workflow_monitor.py`, `tools/agent_tools/waterfall_gate_check.py`, `tools/agent_tools/task_close.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_agent_team_templates.py` | Each consumer adds the exact template upstream; the template lists each selected consumer downstream. |
| `agents/templates/closeout_gate.md` | `tools/agent_tools/task_close.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_agent_team_templates.py` | Existing task-close pair remains; both test consumers and reverse edges are explicit. |
| `agents/templates/design_review.md` | `tools/agent_tools/waterfall_gate_check.py`, `tests/agent_tools/test_waterfall_gate_check.py`, `tests/agent_tools/test_agent_team_templates.py` | The checker and tests list the template upstream; the template lists them downstream. |
| `agents/templates/change_review.md` | `tools/agent_tools/waterfall_gate_check.py`, `tests/agent_tools/test_waterfall_gate_check.py`, `tests/agent_tools/test_agent_team_templates.py` | The checker and tests list the template upstream; the template lists them downstream. |
| `agents/templates/final_review.md` | `tools/agent_tools/report_artifact_checks.py`, `tools/agent_tools/waterfall_gate_check.py`, `tools/agent_tools/task_close.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_waterfall_gate_check.py`, `tests/agent_tools/test_agent_team_templates.py` | Every selected reader lists the template upstream; the template lists every selected reader downstream. |

No durable file adds an upstream or downstream edge to
`reports/agents/convergence-w2-gates-completion-20260716/*`.

## Design-to-Implementation Trace

| Slice | ADF derivation | Paths | Clauses | Required gate |
| --- | --- | --- | --- | --- |
| S1 Canonical schema/state ownership | One aggregate authority responsibility | `COMMUNICATION_PROTOCOL.md`, `CODEX_WORKFLOW.md`, `REVIEW_PROCESS.md` | D1, D2, D3, D5 | Canonical owner review |
| S2 Ledger writer/resolver | Append and resolve one authority head | `work_log.py`, `workflow_monitor.py` | D1, D2 | Targeted public ledger/monitor tests |
| S3 Pure projection and group predicates | Compute only from selected ledger state | `report_artifact_checks.py` | D1, D2, D3, F1-F3 | Checkpoint code review |
| S4 Closeout/design-gate consumers | One public closeout and identity decision | `task_close.py`, `waterfall_gate_check.py` | D1, D5, F1, F4 | Public CLI/gate tests |
| S5 Canonical projections/templates | Keep owner docs as source and readers as projections | skills, workflow, config, templates in Side-Effect Map | D4, D5, F6 | Document-flow and dependency review |
| S6 Public typed negative tests | Preserve observable typed boundaries | five test paths in Side-Effect Map | D1-D3, D5, F5 | Independent test/oracle review |
| S7 Source freeze | Freeze all S1-S6 source/docs/tests together | implementation source commit `S` | D1-D5, F1-F6 | Source tuple readback |
| S8 External implementation review | Review exact `S` tuple | external `IR` artifact | D5, F4-F6 | Independent `APPROVE` |
| S9 Decision binding | Bind prior nodes without self identity | ordered interface commit `B` | D2, D5, F4, F6 | Integration consumer |
| S10 Consolidated validation/closeout | Produce real evidence only | OOP/SOLID/formatter/tests/closeout artifacts | F5, F6 | Auditor/verifier |

Each implementation slice must cite this artifact section and the listed
clause IDs before editing. A missing name, schema field, path, predicate,
transition, test oracle, or dependency edge returns to detailed design review;
the worker must not add a local wrapper or alternate route.

## Exact Acceptance Predicates

### D1

`D1=pass` if and only if:

1. the selected `completion_authority.v1` schema is owned by
   `COMMUNICATION_PROTOCOL.md`;
2. all listed recomputation inputs exist in one full snapshot event;
3. exactly one valid logical key/head is selected through the revision chain;
4. missing, duplicate, forked, invalid-transition, binding, writer, and branch
   errors use the exact typed identities above;
5. the public signatures match this design; and
6. `completion_coverage_consumer(report_dir)` receives no stored or caller
   success authority.

### D2

`D2=pass` if and only if every listed owner/schema/constant/topology/interface/
test consumer uses
`convergence_w2_gate_completion_authority`, the stale value is accepted only as
a negative fixture, and generic branch guards remain generic.

### D3

`D3=pass` if and only if every group first passes exact member-to-event
correspondence, then every resolved member exactly equals the deterministic
baseline on all seven fact fields including ordered `evidence_refs`; any
disagreement produces the specified typed error.

### D4

`D4=pass` if and only if:

1. both canonical owner documents are edited in the source implementation;
2. every selected projection/template/code/test path in the Side-Effect Map is
   updated or explicitly rejected by review with evidence;
3. every durable dependency edge has its exact reverse with matching kind;
4. duplicate current work-log/monitor header edges are normalized; and
5. no durable manifest points to this or any other run-local report.

### D5

`D5=pass` if and only if:

1. `DR` approves exact `D`;
2. `S` descends from `D` and is frozen before `IR`;
3. `IR` independently approves exact `S`;
4. `B` descends from `S` and binds `D`, `DR`, `S`, and `IR`;
5. the interface contains no identity derived from its own bytes or containing
   commit/tree;
6. the external closeout receipt supplies `B` and interface identity after
   commit; and
7. the integration consumer independently verifies the full chain and selected
   authority topology.

### F5 retained test and validation contract

The public typed negative plan remains mandatory:

1. hand-written `coverage_check`, gate, boundary, topology-error, or completion
   mutation;
2. missing authority event;
3. duplicate revision, multiple head, revision gap, supersedes mismatch,
   multiple logical key, invalid transition, and binding/writer mismatch;
4. stale branch reason;
5. group member missing, duplicate, source mismatch, member-set mismatch,
   cross-owner/unit/outcome/evidence mismatch;
6. `source_freeze_before_review=false`;
7. topology field missing, duplicate, or order mutation;
8. design review tuple missing/mismatch/stale;
9. implementation review artifact missing/hash mismatch/not approved;
10. decision-binding interface self-identity attempt or source-ancestor
    mismatch.

Tests begin from writer-generated temporary fixtures and exercise public
work-log, monitor, task-close, and waterfall-gate boundaries. Synthetic test
fixtures are not closeout evidence and are never committed as hand-written pass
artifacts.

Validation status for this design successor:

- `oop_readability=pending`
- `solid_evidence=pending`
- `formatter=pending`
- `targeted_tests=pending`
- `python_execution=deferred_by_user`
- `ci=deferred_by_user`
- `dynamic_graph=deferred_by_user`
- `implementation_authorization=blocked_until_independent_v2_design_approval`

No formatter, Python, test, CI, or dynamic graph result may be promoted to
`pass` by prose. Real artifacts are created only by the owning consolidated
validation route after implementation exists.
