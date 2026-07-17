# W2 F1-F6 Repair Design

<!--
@dependency-start
contract design
responsibility Defines the implementation-ready design for the W2 completion-coverage gate repair.
upstream design ../../../documents/runtime-profiles-and-check-matrix.md owns validation profile and failure-response routing.
upstream design ../../../documents/object-oriented-design.md owns replaceable responsibility and typed-boundary design vocabulary.
upstream implementation ../../../tools/agent_tools/work_log.py owns the canonical semantic ledger.
upstream implementation ../../../tools/agent_tools/report_artifact_checks.py owns the completion-coverage projection and predicates.
downstream implementation ../../../tools/agent_tools/task_close.py consumes the checked completion projection.
downstream implementation ../../../tools/agent_tools/workflow_monitor.py records typed semantic evidence into the ledger.
downstream implementation ../../../tests/agent_tools/test_task_start_and_close.py verifies the public closeout boundary.
downstream implementation ../../../tests/agent_tools/test_work_log.py verifies the ledger boundary.
downstream implementation ../../../tests/agent_tools/test_workflow_monitor.py verifies monitor preservation.
upstream design ./ordered_integration_interface.json records the predecessor integration identity and topology.
@dependency-end
-->

## Design status and request clauses

This is a design-stage artifact only. It authorizes no source, test, hook,
interface, or documentation implementation. Independent detailed-design review
must approve this artifact before a worker edits the implementation paths.

The request clauses are recorded as the following stable IDs:

- `W2-F1`: reject hand-written completion gate and boundary mutations; make the
  canonical ledger and its fingerprinted projection authoritative.
- `W2-F2`: require per-member canonical source-event correspondence for owner,
  responsibility, outcome, and evidence; never infer member facts from group
  fields.
- `W2-F3`: enforce `source_freeze_before_review == true` and exact topology
  state, order, and identity predicates, fail-closed.
- `W2-F4`: repair the ordered integration interface identity so it binds the
  exact frozen source commit/tree, after that source is frozen.
- `W2-F5`: add typed public negative tests for hand-written mutation, member
  mismatch/missing, freeze false, and topology missing/order mutation; retain
  OOP/SOLID/formatter/test evidence as pending until consolidated validation.
- `W2-F6`: provide the abstract frame, source packet, side-effect map,
  clause-to-path trace, publication ordering, and acceptance predicates needed
  for independent design review and implementation handoff.

## Abstract Design Frame

### Responsibility model and replaceable unit

The replaceable responsibility unit is the **canonical completion-coverage
authority**: reconstruct the append-only semantic ledger `L`, produce the
deterministic projection `P = f(L)`, recompute coverage/topology/completion
predicates from that projection and canonical state, and expose the result to
the closeout consumer. Its boundary is the existing `work_log.py` →
`report_artifact_checks.py` → `task_close.py` path, with
`workflow_monitor.py` retaining structured evidence at the ledger boundary.

An alternative implementation can replace this unit only if it preserves the
existing schemas and public consumer boundary, the ledger snapshot digest, the
per-member correspondence rules, and the exact topology predicates below.
There is no new class, CLI flag, config key, public function, or compatibility
route in this design. Existing functions and fields are extended in place,
following their current module ownership.

### Concept and data-flow frame

```text
canonical work-log events L
        │  immutable snapshot + ledger_snapshot_digest
        ▼
projection P (deterministic function of L)  ── projection-only stored view, fingerprint-bound
        │
        ├── recompute check_completion_coverage(P, ...)
        ├── recompute evaluate_completion_boundary(..., topology from L)
        └── task_close consumes only those recomputed typed results
```

`L` is the sole authority for facts that determine clause coverage, ownership,
member correspondence, gate evidence, source freeze, topology, open repairs,
and completion. The existing `control_topology_ledger_snapshot` mapping is
captured as structured evidence on the canonical publication-state ledger
event through the existing `gate_evidence` passthrough; it is not retained as
an independent completion input. `P` is a pure reader projection.
`completion_coverage.json`,
its `coverage_check`, and its `completion_boundary` are stored views only;
they are never success authorities. Every stored view carries the ledger
snapshot identity/digest and source binding. A consumer must reject any
missing, stale, or mismatched fingerprint before considering a success value.

Consumers recompute gate results, topology errors, and completion flags from
`L`/`P`; they do not trust stored `ok`, `gate_results`,
`overall_delivery_complete`, or `topology_errors`. If a stored view is kept
for human/read-model use, it must equal the recomputed result byte-for-byte at
the corresponding structured field boundary.

### Invariants and non-goals

The invariants are:

1. `read_ledger_snapshot` reconstructs one immutable event set and its stable
   digest; all decision-bearing fields are obtained from that snapshot.
2. `project_completion_coverage` is deterministic for a fixed `L`, schema, and
   source binding. The projection metadata binds run, context, source refs,
   snapshot identity, and snapshot digest.
3. Direct coverage has one source event for one clause. Group coverage has one
   source event for each member clause; the group identity and declared member
   set are checked, not used to fill member facts.
4. A non-groupable semantic kind remains non-groupable. Group member events
   must have distinct event identities, exact clause identity, and complete
   owner/responsibility/outcome/evidence fields.
5. Freeze and topology validation is exact and fail-closed. Missing, false,
   reordered, duplicated, or identity-mismatched topology data is an error.

This design does not add a second ledger, persist a second completion state,
reintroduce `run_docs_checks.sh`, alter unrelated OOP score surfaces, add a
runner/scheduler, or implement any W2 code in this slice.

## Implementation Source Packet

### Frozen predecessor and review inputs

The source packet is bound to the exact predecessor, not to a later local
checkout state:

- predecessor commit: `80e63c4134058204e243c6140522d9e3671f9de6`
- predecessor tree: `5174b0dc1426e6afe8db78ba5f43a2320e79feef`
- predecessor branch context: `codex/convergence-w2-gates-completion-writer-owned`
- required independent review artifact:
  `/mnt/l/workspace/agent-canon-convergence-w2-writer-owned/reports/agents/convergence-w2-gates-completion-20260716/reviewer_final_80e63c.md`
- review artifact SHA256:
  `89a150600c30cbfa238e445b7d9bfa0f5dec53818332abe1e0543e83ee366f7a`
- review artifact Git blob:
  `728b8c36ccaaa5ee41babcb25831ba23a51bd4bc`
- predecessor ordered-interface blob:
  `0d72364dc37db1d0241d40444dbca15ea4cb95ec`
- predecessor ordered-interface SHA256:
  `40aa042eb2222f7576613edaf3c93eed7088f3461ec87e3d5d3b93fa0c502aa8`

The review artifact is a required read-before-edit input. Its findings are
F1–F6 in this design; the stale `repaired_commit`/`repaired_tree` in the
predecessor ordered interface is treated as an F4 defect, not as an authority.

### Read-before-edit files and sections

The future implementation worker must read this complete packet in the listed
order before editing:

1. This artifact, especially the Abstract Design Frame, Side-Effect Map,
   Design-To-Implementation Trace, and acceptance predicates.
2. The review artifact above and the predecessor
   `reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json`.
3. `tools/agent_tools/work_log.py`: ledger constants and event validation at
   lines 1–145; append, snapshot reconstruction, and digest at lines 202–279.
4. `tools/agent_tools/report_artifact_checks.py`: completion schemas and
   topology constants at lines 97–186; topology validation at 308–362; event
   mapping at 463–501; projection/fingerprint at 618–887; coverage checks at
   890–1409; artifact writing at 1414–1460; boundary recomputation and
   checked-consumer helpers at 1515–1668.
5. `tools/agent_tools/task_close.py`: the completion consumer at 336–620 and
   its closeout integration at 669–729.
6. `tools/agent_tools/workflow_monitor.py`: passthrough and semantic-event
   decoding at 1–40 and 512–590; ledger append at 1341–1360.
7. Existing public-boundary tests:
   `tests/agent_tools/test_task_start_and_close.py` fixture and closeout tests
   around 520–635 and 3063–3185;
   `tests/agent_tools/test_workflow_monitor.py` typed semantic-event test
   around 150–245; and `tests/agent_tools/test_work_log.py` run-log boundary
   tests.
8. Design and validation authorities:
   `documents/runtime-profiles-and-check-matrix.json` and its Markdown
   projection, `documents/object-oriented-design.md`,
   `documents/tools/agent-canon.md`,
   `documents/dependency-contract-kinds.toml`, and the dependency headers of
   every path in the side-effect map.

No Python execution, test execution, CI, dynamic graph, or source mutation was
used to construct this packet, consistent with the request. Read-only
`find`/`tree`/`git grep`/`grep`/`sed` evidence and the supplied review artifact
are the current evidence level.

## Detailed design contract

### 1. Canonical ledger and projection (`W2-F1`)

`work_log.py` remains the append-only ledger owner. The implementation must
make the snapshot used for completion include every decision-bearing semantic
event, including typed topology/state evidence. Any existing non-routing
arguments used while writing a projection are inputs to the canonical ledger
snapshot contract, not an independent stored success source.

`project_completion_coverage` remains the sole projection route. Its output
must include the exact ledger snapshot identity and digest in
`projection_metadata`; the source binding and all semantic event identities
must match that snapshot. No completion artifact may be accepted without this
fingerprint binding.

The existing `control_topology_ledger_snapshot` argument is therefore used only
while creating or validating the canonical publication-state ledger event. A
consumer resolves the topology mapping back from `L`; it must not accept a
separate caller-supplied topology object whose values can disagree with `L`.

`generated_completion_coverage_errors` and the closeout consumer must perform
the following sequence:

1. read `L` and recompute `P = f(L)`;
2. recompute `check_completion_coverage` and
   `evaluate_completion_boundary` from `P` and canonical typed state;
3. compare every stored projection field, including `coverage_check` and
   `completion_boundary`, with the recomputed values; and
4. only then apply the typed schema checks and return the recomputed result.

The comparison must reject a hand-written artifact that preserves all
semantic projection fields but changes only `coverage_check`, one gate result,
`ok`, `completion_boundary`, `topology_errors`, or a completion boolean.

### 2. Per-member source-event correspondence (`W2-F2`)

For a direct mapping, `clause_id` and `member_clause_ids` contain exactly one
identical clause ID and the mapping has one source event.

For a group mapping, each member has a distinct canonical ledger source event:

- each member event has `clause_id` equal to that member;
- each member event has a distinct `event_id`/`source_event_ref`;
- each member event declares the exact same complete member set and
  `group_identity`; and
- each member event independently supplies `owner`, `state_owner`, `api_owner`,
  `dependency_owner`, `responsibility_unit`, `outcome`, and `evidence_refs`.

The group identity is only a set-membership key. The checker must index group
coverage by the member event's own `clause_id`, require every declared member
exactly once, and compare the projection row to that member's source event.
It must not compare or copy a group-shared facts tuple, select the first event,
or infer missing owner/responsibility/outcome/evidence from a sibling. A
missing member event and every per-member field mismatch are typed errors.
`responsibility_unit`, `decision`, `failure`, `deferral`, and
`publication_state` remain forbidden group semantic kinds.

### 3. Exact freeze, topology, and identity (`W2-F3`)

The topology checker must require all of the following, with no truthiness or
partial-list fallback:

- `source_freeze_before_review is True` exactly;
- `topology_schema == "agent-canon.control-topology.v1"`;
- `topology_order == ["design_approved", "writer_released", "source_frozen", "change_review_approved"]` exactly, with no omission, duplicate, or reorder;
- `formatter_static_events` is the exact ordered event list from the canonical
  snapshot. For the current pending predecessor state it is
  `["static_shell_inspection_recorded", "git_diff_check_passed", "formatter_deferred_by_user"]`;
  a later real formatter run may replace the deferred event only by appending
  its actual typed ledger evidence.
- `writer_cardinality == 1` and `writer_collision_state == "collision_preserved"`;
- `branch_creation_reason == "convergence_w2_writer_owned_after_git_index_blocker"`;
- `run_id`, `context_id`, `observation_ref`, and `source_refs` match the same
  source binding and ledger snapshot;
- `writer_release_order_complete`, `final_review_approved`, and
  `closeout_unlocked` are present booleans and are read from the canonical
  topology event; and
- `global_publication_state`, `routing_gate`, and
  `descendant_disposition` are present and exactly equal to the canonical
  snapshot, not merely non-empty. For the current predecessor topology the
  descendant disposition identity is
  `{status: "none", release: "not_applicable", retained: "two incident checkouts preserved"}`;
  a later stage may change it only through a new canonical ledger event.

For a final delivery result, the canonical state must additionally be
`writer_release_order_complete == true`, `final_review_approved == true`,
`closeout_unlocked == true`, `global_publication_state == "publication_ready"`,
and `routing_gate == "verified"`, with no topology errors. A pending-review
snapshot may retain the predecessor's `writer_fixed_pending_independent_review`,
`writer_owned_pending_review`, `false`, and `false` values, but it cannot be
reported as complete. The `G5_DELIVERY_BOUNDARY` value must be recomputed and
must equal the recomputed `overall_delivery_complete` value.

### 4. Non-self-referential publication (`W2-F4`, `W2-F6`)

Publication is a two-commit sequence after design approval:

1. Commit the implementation/test source changes and freeze that source
   commit/tree. The source-freeze identity is established before any evidence
   binding is written.
2. In a later evidence-binding change, update the existing ordered-interface
   `repair_identity.repaired_commit`, `repair_identity.repaired_tree`, and
   corresponding diff identity to the already-frozen source commit/tree; then
   perform independent review against that identity.

The ordered interface and review/evidence artifacts are not part of the source
implementation freeze commit when they contain its repaired commit/tree. No
file may require the commit or tree that contains that same file. This design
document binds only the predecessor identity above and intentionally contains
no field for its own containing commit/tree.

## Design Side-Effect Map

| Surface | Owner-stage change | Review gate | Validation/test-plan item | Clauses / reuse |
|---|---|---|---|---|
| `tools/agent_tools/work_log.py` | Keep append-only `L`; enforce per-member source-event identity and canonical topology/state capture; retain digest semantics. | Detailed design, then implementation review. | Typed ledger read/write boundary; missing/mismatch and freeze/topology cases. | `W2-F2`, `W2-F3`; reuse `append_ledger_event`, `_validate_ledger_event`, `read_ledger_snapshot`, `ledger_snapshot_digest`. |
| `tools/agent_tools/report_artifact_checks.py` | Make `P=f(L)` the only projection; compare/recompute `coverage_check` and `completion_boundary`; replace group-facts inference with per-member checks; exact topology predicates. | Detailed design, independent source review, final artifact review. | Public completion artifact mutation cases; all G1–G5 are derived, not accepted from stored booleans. | `W2-F1`–`W2-F3`; reuse existing schema constants and projection/check/boundary functions. |
| `tools/agent_tools/task_close.py` | Verify fingerprint and canonical recomputation before reading any stored success field; consume only recomputed typed results. | Closeout review after source freeze. | Subprocess invocation of the `task_close.py` CLI for every negative case. | `W2-F1`, `W2-F3`, `W2-F5`; reuse `completion_coverage_consumer` and `consume_checked_completion_coverage` as consumer seams. |
| `tools/agent_tools/workflow_monitor.py` | Preserve structured member, existing `group_identity`, gate, topology, and failure evidence into `L`; do not synthesize success values in monitoring text. | Runtime-surface review if the event payload changes. | Typed semantic-event public CLI round trip, including member refs, `group_identity`, and binding. | `W2-F2`, `W2-F5`; reuse `semantic_event_record`, `append_monitoring`, and existing passthrough fields. |
| `tests/agent_tools/test_task_start_and_close.py`, `test_work_log.py`, `test_workflow_monitor.py` | Add only typed public-boundary regressions; start from generated valid fixtures and mutate one field per negative case. | Independent test/oracle review after implementation mechanism exists. | Hand-written gate mutation; member mismatch/missing; freeze false; topology missing/order mutation; positive control generated by the writer. | `W2-F5`; reuse subprocess boundaries and current fixture builders. No private helper or scalar score oracle. |
| `.codex/hooks/oop_readability_guard.py`, `tools/agent_tools/check_solid_evidence.py`, `tools/oop/shared/readability_core.py` | No behavior change in this design slice. Future evidence must remain typed and treat `STATUS_REVIEW` as warning/log, not hook failure. | Consolidated OOP/SOLID validation. | Actual changed-path report with `scanned_paths`/`covered_paths`, then SOLID evidence check. | `W2-F5`; reuse current typed evidence fields and `SOLID_PRINCIPLES_BY_KIND`. |
| `reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json` | Later evidence-binding update only: rebind repaired identity to the frozen source commit/tree and add this design path/sections and clause trace. Not edited now. | Independent review must be against the exact frozen identity. | Static identity comparison and review artifact binding. | `W2-F4`, `W2-F6`; reuse existing `repair_identity`, `review`, and `topology` fields. |
| `documents/runtime-profiles-and-check-matrix.*`, `documents/tools/agent-canon.md`, Rust docs path, and dependency headers | Authority/read-only surface in this design slice. If implementation changes dependency edges, update only the owning header and its reverse edge; do not add a docs checker or overwrite generated projections. | Document-flow/dependency review only if implementation changes these surfaces. | Non-Python canonical docs check when selected; changed-file header checks in consolidated validation. | `W2-F5`, `W2-F6`; reuse runtime-profile JSON authority, Markdown projection, and `tools/bin/agent-canon docs`. |

No source, test, hook, interface, or documentation path in this map is edited
by this design commit. The only changed path is this design artifact.

## Design-To-Implementation Trace

| Future slice | Abstract-frame section | Request clauses | Planned paths | Reuse and validation |
|---|---|---|---|---|
| S1: authoritative projection and gate recomputation | Canonical ledger/projection; Detailed design 1 | `W2-F1` | `report_artifact_checks.py`, `task_close.py` | Extend existing projection/check/boundary seams; public JSON/CLI mutation test; fingerprint mismatch is fail-closed. |
| S2: member correspondence | Responsibility model; Detailed design 2 | `W2-F2` | `work_log.py`, `report_artifact_checks.py`, `workflow_monitor.py` | Use existing `member_clause_ids`, `group_identity`, `source_event_ref`; one source event per member; typed missing/mismatch tests. |
| S3: freeze/topology exactness | Invariants; Detailed design 3 | `W2-F3` | `report_artifact_checks.py`, `task_close.py`, topology ledger path in `work_log.py` | Reuse current topology schema/order constants; exact equality tests for false, missing, duplicate, and reorder. |
| S4: monitor preservation | Concept/data-flow frame | `W2-F2`, `W2-F3` | `workflow_monitor.py`, `work_log.py` | Preserve structured JSON, `member_clause_ids`, and existing `group_identity` at the monitor-to-ledger seam; public round-trip test. |
| S5: typed public negative suite and consolidated evidence | Evaluation axes and validation contract | `W2-F5` | `tests/agent_tools/test_task_start_and_close.py`, `test_work_log.py`, `test_workflow_monitor.py` | Start from a generated valid artifact; mutate only one typed field; invoke public CLI/module boundaries. OOP/SOLID/formatter/test status stays pending until real artifacts exist. |
| S6: evidence publication binding | Non-self-referential publication | `W2-F4`, `W2-F6` | `ordered_integration_interface.json` and later review artifact | Source freeze commit/tree first; later interface/review artifact references it; no self-binding. |
| S7: dependency/document follow-through | Side-Effect Map documentation/header row | `W2-F6` | Only mechanically selected headers/docs | Preserve canonical docs route and reverse dependency edges; no new API or checker route. |

## Typed public negative-test plan

These are planned tests, not executed evidence. Each test must begin with a
valid artifact generated by the existing writer path and must invoke the
public `task_close.py` boundary (or the public monitor/work-log boundary when
that is the behavior under test). A test must inspect typed JSON/result fields,
not private helpers, line counts, scalar OOP scores, or success prose.

1. **Hand-written gate mutation (`W2-F1`)**: generate a valid projection, then
   mutate only `coverage_check.error_sets`, one `gate_results` value, `ok`,
   `completion_boundary.topology_errors`, or one completion boolean. The
   closeout CLI must return not-ready with a typed stale/generated-projection
   mismatch. The same test must cover a digest mutation and a stored-view-only
   mutation.
2. **Group member mismatch (`W2-F2`)**: generate two distinct member source
   events under one group identity, then alter member B's owner,
   responsibility unit, outcome, or evidence refs in the stored projection.
   The consumer must reject the per-member correspondence mismatch even when
   member A and all group fields remain valid.
3. **Group member missing (`W2-F2`)**: remove member B's canonical source event
   or its coverage row while leaving the declared group set A/B. The typed
   error must identify the missing member/source-event correspondence; no
   sibling event may cover B implicitly.
4. **Freeze false (`W2-F3`)**: use the generated writer with
   `source_freeze_before_review=False` (not a hand-written pass artifact) and
   invoke the closeout CLI. It must reject the snapshot even when all other
   fields are populated and must expose a topology/freeze error.
5. **Topology missing and order mutation (`W2-F3`)**: generate separate
   snapshots with one required topology field omitted and with the exact
   `topology_order` swapped or duplicated. The consumer must reject each with
   typed topology errors; a partially valid order is not accepted.
6. **Monitor preservation (`W2-F2`, `W2-F5`)**: submit a typed semantic event
   through the existing monitor CLI containing member and source-binding
   fields, then read the canonical ledger event and assert structured values
   are preserved without a synthesized success field.

## Validation state and evidence policy

Current design-stage evidence is static/read-only only: clone provenance,
exact commit/tree resolution, review-artifact SHA/blob verification, source
reading, `git grep`/`grep`/`find`/`tree` inspection, and `git diff --check`.
The requested restrictions mean the following remain typed pending and must
not be represented by hand-written `pass` artifacts:

| Evidence | Design-stage state | Later owner route |
|---|---|---|
| OOP readability | `pending` | actual changed-path OOP report with `scanned_paths` |
| SOLID evidence | `pending` | actual `check_solid_evidence.py --changed --evidence` result with covered paths |
| formatter/docs check | `pending` | non-Python `tools/bin/agent-canon docs check`/format route when the design artifact or implementation docs are selected |
| targeted tests | `pending` | public typed negative suite after the owning mechanism exists |
| Python, CI, dynamic graph | `deferred_by_user` | consolidated validation only if the active profile selects them |

The scoped non-Python formatter/check used while drafting this Markdown passed
with no file changes. That is document hygiene evidence only; it does not
populate the consolidated implementation formatter gate, whose typed status
remains `pending` until the owning implementation and its complete validation
run exist.

The current checkout has the non-Python `tools/bin/agent-canon` route
available, but this design-only commit does not create a formatter pass
artifact. A later consolidated validation run must execute the canonical route
and record its real result. Any validation failure must first record
`failing_contract`, `observation_level`, `cause_classification`,
`intent_preservation`, and evidence before changing intent, oracle, or scope.

No standalone `test_plan.md` or hand-written OOP/SOLID/formatter/test result is
created here: the active request asks for the typed plan in this design, while
post-implementation test design is not activated until the owning mechanism
exists.

## Acceptance predicates for F1-F6

- **F1**: For every completion artifact, `L` can be reconstructed; its digest
  and source binding match `P`; recomputed coverage and boundary objects equal
  the stored objects; all G1–G5 values are derived from that recomputation;
  mutating only a stored success value makes `task_close` not-ready.
- **F2**: Every covered direct clause maps exactly once to its source event;
  every group member has exactly one distinct canonical source event and
  independently matching owner/responsibility/outcome/evidence; missing or
  mismatched members produce typed errors; no forbidden semantic kind groups.
- **F3**: `source_freeze_before_review is True`; the complete topology schema,
  exact order, exact identity fields, cardinality, collision, state values,
  and bindings match `L`; any missing/false/reordered/duplicated topology
  input makes all affected gates fail closed.
- **F4**: The later ordered interface records the actual already-frozen source
  implementation commit/tree and diff identity, and independent review
  resolves that exact identity. It does not point at its own containing commit
  or tree.
- **F5**: The public negative suite covers all six typed cases above; actual
  OOP/SOLID/formatter/test artifacts are produced only by their owning tools;
  no hand-written pass artifact can unlock completion.
- **F6**: This artifact is independently reviewable and implementation-ready:
  it contains the Abstract Design Frame, exact predecessor/review Source
  Packet, Side-Effect Map, clause-to-path trace, publication ordering, and
  all acceptance predicates. The next gate is independent detailed-design
  review; implementation is blocked until that gate approves this artifact.

## Gate handoff

`design_review_status=pending_independent_review`.
`implementation_authorization=blocked_until_design_review_approved`.
`source_changes_in_this_commit=none`.
`test_execution_in_this_commit=none`.
