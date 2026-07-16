# W2 F1-F6 Repair Design v3

## Reader Map

- Purpose: close only R1-R3 from the independent recheck of the `1413d1ef`
  design while preserving the design-ready D2, D3, F1, and F2 contracts.
- Audience: canonical owner editors, the W2 implementation writer,
  independent design and implementation reviewers, and the parent/W3
  integration consumer.
- Reader order: Request Clauses → Owner Surfaces → Selected Architecture →
  Rejected Alternatives → Abstract Design Frame → Implementation Source Packet
  → Design Side-Effect Map → Design-to-Implementation Trace → Exact Acceptance
  Predicates.
- Artifact relation: this file is an append-only successor to
  `w2_f1_f6_repair_design_v2.md`. It supersedes v2 for future implementation
  authority after independent approval; v1, v2, and their review artifacts
  remain historical evidence.
- First artifact: the R1 canonical Git tree-delta byte contract. It fixes the
  exact bytes reviewed at `S` and the exact one-path delta permitted at `B`.
- Structure contract:
  - `structure_kind=document`
  - `document_unit=run-local detailed-design successor`
  - `document_split_decision=split:R1-R3 require an independently reviewable append-only successor while prior decisions remain evidence`
  - `structure_visual_plan=table:byte layout, truth tables, publication nodes, and dependency pairs require exact repeated fields rather than a lossy process rendering`
  - `structure_source_map=v2 design plus the supplied v2 recheck decision to R1-R3 sections below`
  - `structure_oop_contract=one replaceable completion-authority responsibility unit`
  - `discourse_relations=not_required`
  - `prose_graph_execution=not_run_by_user_constraint`
  - `structure_invalid_interpretations_recorded=yes`
- Dependency classification: this is a run-local report under `reports/`.
  Durable dependency manifests must not point to this artifact or any other
  run-local report. The Implementation Source Packet records read bindings in
  prose only.
- Invalid interpretations:
  - this artifact is not implementation authorization;
  - this artifact creates no source, test, owner-document, hook, template, or
    ordered-interface change;
  - Git command output is not the canonical diff serialization;
  - a non-empty string, stored boolean, copied topology, or hand-written pass
    artifact is never acceptance evidence;
  - this artifact does not contain its own commit, tree, blob, or SHA256.

## Request Clauses

- `R1-CANONICAL-TREE-DELTA`: define one canonical Git tree-delta serialization,
  one inclusive byte range for SHA256, mechanically derived `changed_paths`,
  exact direct-parent and interface-only `B` predicates, typed failures, and
  public negative tests.
- `R2-EXACT-TOPOLOGY-EVIDENCE`: define a complete truth table for every normal
  state plus `repair_pending` and `escalation_pending`; define exact
  `repair_return_state`, formatter/static records, descendant disposition,
  typed failures, and public negatives without non-empty-text fallbacks.
- `R3-REVIEW-POLICY-DEPENDENCY-CLOSURE`: define exact durable
  `documents/REVIEW_PROCESS.md` owner-to-consumer edges and matching reverse
  edges, including direct consumers found by static enumeration, without any
  durable edge to run-local reports.
- `D1-CANONICAL-AUTHORITY`: retain one full-snapshot
  `completion_authority` aggregate event in the canonical ledger as the sole
  authority.
- `D2-BRANCH-REASON`: retain the single canonical value
  `convergence_w2_gate_completion_authority`.
- `D3-GROUP-EQUALITY`: retain per-member canonical source-event
  correspondence followed by exact cross-member equality.
- `D4-OWNER-AND-DEPENDENCY-CLOSURE`: retain canonical owner-first edits,
  projection consumers, tests, and bidirectional dependency headers.
- `D5-NON-SELF-REFERENTIAL-PUBLICATION`: retain an acyclic
  design-review-source-review-binding-closeout chain in which no artifact
  hashes its own bytes or requires its own containing Git identity.
- `W2-F1` through `W2-F6`: retain the accepted F1-F6 repair intent.
- `W2-F5`: retain public typed negative tests and honest
  `pending`/`deferred_by_user` validation states; never manufacture pass
  evidence.
- `DESIGN-ONLY-V3`: this commit adds only this successor artifact.

## Owner Surfaces

| Surface | Canonical responsibility | v3 decision |
| --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` `CompletionCoverage v1 Schema Contract` | Ledger event, authority payload, source correspondence, and review packet semantics | Retains the aggregate `completion_authority` schema, exact member correspondence, and exact formatter/descendant record schemas. |
| `agents/canonical/CODEX_WORKFLOW.md` `CompletionCoverage Applicability And State Contract` | Applicability, state transitions, topology truth, and W2 branch reason | Owns the normal-state truth tables, repair/escalation transition rules, and the sole branch reason. |
| `documents/REVIEW_PROCESS.md` | Review lifecycle, exact target identity, post-fix refresh, merge evidence, and non-self-reference | Owns D→DR→S→IR→B→post-binding-review lifecycle and the R3 downstream dependency declarations. |
| `documents/dependency-manifest-design.md` `Bidirectional Consistency` | Durable dependency edge direction, kind, relative path, reverse matching, and cycle policy | Owns the exact R3 edge pairs. |
| `tools/agent_tools/work_log.py` | Append-only ledger, canonical snapshot, aggregate head resolution | Owns event validation, full-snapshot selection, revision/supersession, and typed authority failures. |
| `tools/agent_tools/workflow_monitor.py` | Public structured event append boundary | Preserves exact aggregate, group, formatter/static, and descendant fields; it never synthesizes success. |
| `tools/agent_tools/report_artifact_checks.py` | Pure projection, boundary checks, topology checks, Git identity checks, ordered integration verifier | Owns the R1 serializer/observer, R2 exact predicates, and full publication verification. |
| `tools/agent_tools/task_close.py` | Public closeout consumer | Reconstructs the ledger and externally verifies `B`; it never trusts stored success. |
| `tools/agent_tools/waterfall_gate_check.py` | Public design/change/final review gate | Verifies exact review target fields and current-tuple approval. |
| `tools/agent_tools/evaluate_agent_run.py` | Review artifact evaluation consumer | Uses refreshed change/final review identities and decisions rather than stale artifact presence. |
| `tools/agent_tools/agent_team.py` | Review packet and role-document materialization | Routes `REVIEW_PROCESS.md` and exact review templates to the selected review roles. |
| `tools/agent_tools/check_convention_compliance.py` and `tool_drift.py` | Durable marker/header and reverse-edge checks | Enforce the owner/consumer headers and reject missing or mismatched reverse edges. |
| Run-local reviews, ledgers, closeout receipts, and ordered interface | Evidence/projection only | May bind canonical source facts but cannot replace owner docs or the selected authority event. |

## Selected Architecture

### Decision

Retain the v2 selection: one full-snapshot canonical aggregate
`completion_authority` event on the existing non-groupable
`publication_state` semantic kind.

The canonical ledger is `L`. CompletionCoverage, topology, gates, publication
readiness, and stored interface views are pure projections:

`P = f(L, Git object readback, externally supplied decision-binding commit)`.

The aggregate event is part of `L`; it is not a second ledger. No aggregate
event or projection stores authoritative `ok`, G1-G5 pass values,
`all_planned_chunks_complete`, `overall_delivery_complete`, or
`integration_ready`. Consumers recompute those values and reject any stored
success mutation.

### Canonical aggregate event

The event envelope remains:

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
  "evidence_refs": ["<ordered unique canonical source references>"],
  "artifact_refs": ["<ordered unique run artifact references>"],
  "source_binding": {
    "run_id": "<run_id>",
    "context_id": "<context_id>"
  },
  "completion_authority": {}
}
```

Exact envelope predicates:

1. `semantic_kind` is exactly `publication_state`.
2. `clause_id`, `mapping_mode=group`, `group_identity`, and
   `member_clause_ids` are forbidden on the aggregate event.
3. `owner` and `state_owner` equal
   `completion_authority.source_binding.component_manager`.
4. `outcome` equals `completion_authority.transition_state`.
5. Envelope, logical key, nested source binding, topology, and all
   participating events agree exactly on `run_id` and `context_id`.
6. `evidence_refs` and `artifact_refs` are ordered, duplicate-free arrays.
   Their entries must resolve to the expected canonical source event or
   artifact; non-empty text alone does not satisfy the predicate.

Every aggregate revision carries all of these fields:

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
    "assigned_unit": "completion_authority",
    "source_binding": {
      "run_id": "<run_id>",
      "context_id": "<context_id>"
    },
    "source_refs": ["<ordered unique source refs>"]
  },
  "active_clause_ids": ["<ordered unique active clause ids>"],
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
  "topology": {}
}
```

`active_clause_ids` follows active-row order in
`user_request_contract.md`. The ledger event is runtime authority; the user
contract is its cited source. Schedule/open-work fields are exact booleans.
`open_repairs` and `open_crossing_edges` are exact typed lists. Missing fields,
truthiness coercion, or caller-supplied substitutes fail.

### D1 ordering, supersession, and public signatures

The logical key is exactly
`{run_id, context_id, authority: completion_authority}`.

Selection is unchanged and fail-closed:

1. Read every ledger event and derive the snapshot identity from canonical
   sorted event bytes. A caller cannot supply a snapshot label.
2. Select exact aggregate schema events on `publication_state`.
3. Require one logical key for the report run.
4. Require exactly one revision `1` with
   `supersedes_event_id=null`.
5. Require one event for every consecutive revision.
6. Require every revision `n > 1` to supersede the exact event ID at `n - 1`.
7. Require `event_id=completion-authority:<context_id>:<revision>`.
8. Require exactly one unsuperseded head and no fork, gap, duplicate, or orphan.
9. Validate transitions against the R2 state rules below.
10. Return the one full head. Never merge fields from multiple revisions.

Stable authority errors remain:

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
- `completion_authority:source_binding_mismatch:<event_id>`
- `completion_authority:writer_owner_mismatch:<event_id>`
- `completion_authority:branch_creation_reason_mismatch`

Exact public signatures remain:

```python
def read_ledger_snapshot(report_dir: Path) -> dict[str, object]:
    ...

def resolve_completion_authority(
    ledger_snapshot: Mapping[str, object],
) -> dict[str, object]:
    ...

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

`completion_coverage_consumer(report_dir)` and
`generated_completion_coverage_errors(report_dir, artifact)` reconstruct the
ledger snapshot internally. Stored views carry the selected event ID, revision,
logical key, and derived snapshot digest. A fingerprint mismatch invalidates
the view.

### D2 branch-reason convergence retained

The only W2 value is:

`convergence_w2_gate_completion_authority`.

The stale value
`convergence_w2_writer_owned_after_git_index_blocker` is permitted only in a
negative fixture. The exact owner and consumer set remains:

| Consumer | Exact contract |
| --- | --- |
| `agents/canonical/CODEX_WORKFLOW.md` | Owns the one value. |
| `agents/COMMUNICATION_PROTOCOL.md` | Carries it in the aggregate topology schema. |
| `work_log.py` | Rejects a head whose topology differs. |
| `workflow_monitor.py` | Preserves it without normalization. |
| `report_artifact_checks.py` | Uses the one constant and emits a typed mismatch. |
| `task_close.py` | Exposes the resolver/verifier mismatch. |
| ordered interface | Carries only the canonical value as a projection. |
| `test_work_log.py` and `test_task_start_and_close.py` | Use the canonical positive and stale negative cases. |

Generic branch-guard placeholders such as
`branch_creation_reason=<reason>` remain generic authority-presence checks.

### D3 member correspondence and group equality retained

Group validation remains two mandatory phases.

Phase 1, per-member correspondence:

1. Every member clause resolves to one distinct canonical source event.
2. The row `source_event_ref` resolves to that exact event.
3. Row and event match on `clause_id`, `group_identity`,
   `member_clause_ids`, `mapping_mode`, semantic kind, owner, state owner,
   API owner, dependency owner, responsibility unit, outcome, and
   `evidence_refs`.
4. Missing or duplicate member events fail before group comparison.
5. No fact is inferred from a group-shared field.

Phase 2, exact cross-member equality:

1. Sort resolved member events by `clause_id`.
2. Use the first event as the deterministic baseline.
3. Require exact equality for `owner`, `state_owner`, `api_owner`,
   `dependency_owner`, `responsibility_unit`, `outcome`, and
   `evidence_refs`.
4. `evidence_refs` must be non-empty, ordered, duplicate-free, and byte-for-byte
   equal as arrays. Set equality is insufficient.

Stable group errors remain:

- `group_member:missing:<group_identity>:<clause_id>`
- `group_member:duplicate:<group_identity>:<clause_id>`
- `group_member:source_event_mismatch:<group_identity>:<clause_id>:<field>`
- `group_member:member_set_mismatch:<group_identity>:<clause_id>`
- `group_member:cross_equality_mismatch:<group_identity>:<field>:<baseline_clause>:<member_clause>`
- `group_member:evidence_not_unique:<group_identity>:<clause_id>`

The existing non-groupable semantic-kind prohibition remains.

### R1 canonical Git tree-delta serialization

The bounded repository object format is exactly `sha1`. The implementation
rejects any other object format for this W2 publication contract rather than
inventing a second encoding.

The canonical interface path constant is exactly:

`reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json`

Its UTF-8 path is 90 bytes. No basename-only comparison is permitted.

The canonical serializer is
`agent-canon.git-tree-delta.v1`. It compares two Git tree OIDs, recursively
flattens non-tree entries, and emits one record for every path whose mode or
object ID differs.

Canonical entry construction:

1. Enumerate the union of leaf paths from `base_tree` and `target_tree`.
2. Construct path bytes directly from Git tree entry-name bytes joined by one
   ASCII slash. Do not quote, escape, normalize Unicode, or use locale collation.
3. Git paths containing NUL are impossible. A path that is not strict UTF-8 is
   rejected because `changed_paths` is a JSON string array.
4. Directory entries are not records. Their changed leaves are records.
5. Rename detection is disabled. A rename is one delete record and one add
   record.
6. Omit a path only when old mode equals new mode and old blob equals new blob.
7. Allowed present modes are `100644`, `100755`, and `120000`. Absent mode is
   `000000`. A changed gitlink or other non-blob mode fails this bounded W2
   contract.
8. Present blob IDs are 40 lowercase hexadecimal SHA-1 bytes. An absent blob is
   40 ASCII zero bytes.
9. Sort records by unsigned lexicographic comparison of the raw path bytes.
   Duplicate path bytes are forbidden.

The serialized byte stream is exactly this concatenation:

```text
"agent-canon.git-tree-delta.v1\0"
"object-format=sha1\0"
"base-tree=" + <40 lowercase ASCII hex> + "\0"
"target-tree=" + <40 lowercase ASCII hex> + "\0"
"entry-count=" + <16 lowercase ASCII hex> + "\0"
for each record:
  "entry\0"
  "path-length=" + <16 lowercase ASCII hex byte length> + "\0"
  "path=" + <raw path bytes> + "\0"
  "old-mode=" + <6 ASCII octal digits> + "\0"
  "new-mode=" + <6 ASCII octal digits> + "\0"
  "old-blob=" + <40 lowercase ASCII hex or 40 ASCII zero bytes> + "\0"
  "new-blob=" + <40 lowercase ASCII hex or 40 ASCII zero bytes> + "\0"
"end\0"
```

All quoted literal fragments above are ASCII bytes. The terminal delimiter is
exactly the four bytes `65 6e 64 00` (`end` followed by NUL). No byte follows
that delimiter.

The SHA256 byte range is exactly the half-open range `[0, byte_length)` of the
complete stream: it starts at the first byte of
`agent-canon.git-tree-delta.v1` and includes the terminal NUL in `end\0`.
It excludes Git command banners, filenames printed by tools, stderr, shell
newlines, prose, JSON rendering, and any trailing byte.

The module-level observer signature is exact:

```python
def observe_git_tree_delta(
    workspace: Path,
    base_tree: str,
    target_tree: str,
) -> dict[str, object]:
    ...
```

It returns:

```json
{
  "schema": "agent-canon.git-tree-delta-observation.v1",
  "serialization": "agent-canon.git-tree-delta.v1",
  "object_format": "sha1",
  "base_tree": "<40 lowercase hex>",
  "target_tree": "<40 lowercase hex>",
  "byte_length": 0,
  "diff_sha256": "<64 lowercase hex>",
  "changed_paths": ["<strict UTF-8 path in record order>"],
  "entries": [
    {
      "path": "<strict UTF-8 path>",
      "old_mode": "100644",
      "new_mode": "100644",
      "old_blob": "<40 lowercase hex or null>",
      "new_blob": "<40 lowercase hex or null>"
    }
  ]
}
```

`changed_paths` is derived only by strict UTF-8 decoding of the serialized
record paths in record order. A caller-supplied path list is not accepted.

R1 source-freeze predicates:

1. Resolve base commit
   `80e63c4134058204e243c6140522d9e3671f9de6` to tree
   `5174b0dc1426e6afe8db78ba5f43a2320e79feef`.
2. Resolve `S` to its exact source tree.
3. Observe the canonical delta from the base tree to the `S` tree.
4. Require `source_freeze.diff_sha256` to equal the observation digest.
5. Require `source_freeze.changed_paths` to equal the observation
   `changed_paths` array exactly, including order.
6. Require the canonical interface path not to occur in that array.
7. Require the interface entry in `S` to remain mode `100644` and blob
   `0d72364dc37db1d0241d40444dbca15ea4cb95ec`.
8. Require `implementation_review.reviewed_source_commit=S`,
   `reviewed_source_tree=S.tree`, and
   `reviewed_diff_sha256=source_freeze.diff_sha256`.

R1 decision-binding predicate, repeated as the named
`R1-BINDING-SHAPE` contract:

1. `B` is a commit with exactly one parent.
2. `parent(B) == S`.
3. The canonical tree delta from `S.tree` to `B.tree` contains exactly one
   record.
4. Its ordered `changed_paths` array is exactly
   `["reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json"]`.
5. The record old mode and new mode are both `100644`.
6. The old blob is exactly
   `0d72364dc37db1d0241d40444dbca15ea4cb95ec`.
7. The new blob is the Git blob of the interface bytes read from `B`, differs
   from the old blob, and equals the externally observed interface blob.
8. Because the canonical delta has one record at the exact path, `B.tree` is
   byte-identical to `S.tree` outside that path.
9. The external closeout/binding observation records the canonical `S→B`
   delta digest and path array; the verifier recomputes and compares both.

R1 stable failures:

- `git_tree_delta:unsupported_object_format:<format>`
- `git_tree_delta:path_not_utf8:<path_hex>`
- `git_tree_delta:non_blob_mode:<path>:<mode>`
- `git_tree_delta:duplicate_path:<path>`
- `git_tree_delta:serialization_mismatch`
- `source_freeze:diff_sha256_mismatch`
- `source_freeze:changed_paths_mismatch`
- `source_freeze:interface_path_changed`
- `source_freeze:interface_mode_mismatch`
- `source_freeze:interface_blob_mismatch`
- `implementation_review:reviewed_source_commit_mismatch`
- `implementation_review:reviewed_source_tree_mismatch`
- `implementation_review:reviewed_diff_sha256_mismatch`
- `ordered_integration:decision_parent_count_mismatch`
- `ordered_integration:decision_parent_not_source`
- `ordered_integration:decision_path_set_mismatch`
- `ordered_integration:decision_extra_path:<path>`
- `ordered_integration:decision_interface_mode_mismatch`
- `ordered_integration:decision_interface_old_blob_mismatch`
- `ordered_integration:decision_interface_new_blob_mismatch`
- `ordered_integration:decision_tree_outside_interface_mismatch`
- `ordered_integration:decision_diff_sha256_mismatch`

### R2 exact topology schema

The topology schema is exactly
`agent-canon.control-topology.v2`:

```json
{
  "run_id": "<run_id>",
  "context_id": "<context_id>",
  "observation_ref": "completion-authority:<context_id>:<revision>",
  "global_publication_state": "context_bound",
  "routing_gate": "pending",
  "writer_release_order_complete": false,
  "source_freeze_before_review": false,
  "final_review_approved": false,
  "decision_binding_complete": false,
  "closeout_unlocked": false,
  "branch_creation_reason": "convergence_w2_gate_completion_authority",
  "source_freeze_identity": null,
  "implementation_review_identity": null,
  "decision_binding_identity": null,
  "formatter_static_events": [
    {
      "schema": "agent-canon.formatter-static-event.v1",
      "record_id": "formatter-static:canonical_formatter",
      "ordinal": 1,
      "check_kind": "canonical_formatter",
      "status": "pending",
      "owner": "<source_binding.component_manager>",
      "source_event_ref": null,
      "artifact_path": null,
      "artifact_sha256": null,
      "artifact_blob": null
    },
    {
      "schema": "agent-canon.formatter-static-event.v1",
      "record_id": "formatter-static:selected_non_python_static",
      "ordinal": 2,
      "check_kind": "selected_non_python_static",
      "status": "pending",
      "owner": "<source_binding.component_manager>",
      "source_event_ref": null,
      "artifact_path": null,
      "artifact_sha256": null,
      "artifact_blob": null
    }
  ],
  "writer_cardinality": 1,
  "writer_collision_state": "collision_preserved",
  "descendant_disposition": {},
  "topology_schema": "agent-canon.control-topology.v2",
  "topology_order": [
    "design_approved",
    "writer_released",
    "source_frozen",
    "change_review_approved"
  ]
}
```

Identity predicates:

- `run_id` and `context_id` equal the selected aggregate logical key.
- `observation_ref` equals the selected aggregate event ID. Merely being
  non-empty is insufficient.
- `global_publication_state` equals `transition_state`.
- `branch_creation_reason`, writer cardinality, collision state, schema, and
  topology order equal the literals above.
- `source_freeze_identity`, when present, has exact
  `{commit, tree, diff_sha256, changed_paths}` fields and matches the R1
  source-freeze observation.
- `implementation_review_identity`, when present, has exact
  `{path, sha256, blob, decision, reviewed_source_commit,
  reviewed_source_tree, reviewed_diff_sha256}` fields, resolves to those bytes,
  says `APPROVE`, and matches the source-freeze tuple.
- `decision_binding_identity`, when present, has exact
  `{commit, tree, parent, diff_sha256, changed_paths, interface_path,
  interface_blob, interface_sha256}` fields and satisfies
  `R1-BINDING-SHAPE`.
- No identity object is accepted because its fields are non-empty.

### R2 normal-state truth tables

Legend: `T=true`, `F=false`. `WR` is writer release, `SF` source freeze before
review, `RV` independent implementation review approval, `DB` verified
decision binding, and `CU` closeout unlock.

| Normal state | WR | SF | RV | DB | CU | `routing_gate` | `repair_return_state` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `context_bound` | F | F | F | F | F | `pending` | `null` |
| `design_pending` | F | F | F | F | F | `pending` | `null` |
| `design_approved` | F | F | F | F | F | `pending` | `null` |
| `writer_release_pending` | F | F | F | F | F | `pending` | `null` |
| `writer_released` | T | F | F | F | F | `pending` | `null` |
| `source_freeze_pending` | T | F | F | F | F | `pending` | `null` |
| `source_frozen` | T | T | F | F | F | `pending` | `null` |
| `change_review_pending` | T | T | F | F | F | `pending` | `null` |
| `change_review_approved` | T | T | T | F | F | `pending` | `null` |
| `integration_pending` | T | T | T | T | F | `pending` | `null` |
| `publication_ready` | T | T | T | T | T | `verified` | `null` |
| `delivered` | T | T | T | T | T | `verified` | `null` |

The exact schedule/open-work table is:

| Normal state | implementation | review | freeze+review | formatter+static | planned work |
| --- | --- | --- | --- | --- | --- |
| `context_bound` | F | F | F | F | F |
| `design_pending` | F | F | F | F | F |
| `design_approved` | F | F | F | F | F |
| `writer_release_pending` | F | F | F | F | F |
| `writer_released` | F | F | F | F | F |
| `source_freeze_pending` | T | F | F | T | F |
| `source_frozen` | T | F | F | T | F |
| `change_review_pending` | T | F | F | T | F |
| `change_review_approved` | T | T | T | T | T |
| `integration_pending` | T | T | T | T | T |
| `publication_ready` | T | T | T | T | T |
| `delivered` | T | T | T | T | T |

The columns map exactly to
`w2_implementation_complete`, `w2_review_complete`,
`source_freeze_review_complete`,
`formatter_and_static_checks_pass`, and `planned_work_complete`.

Normal-state identity presence is exact:

| State range | Source-freeze identity | Implementation-review identity | Decision-binding identity |
| --- | --- | --- | --- |
| `context_bound` through `source_freeze_pending` | `null` | `null` | `null` |
| `source_frozen` through `change_review_pending` | exact R1 source tuple | `null` | `null` |
| `change_review_approved` | exact R1 source tuple | exact approved IR tuple | `null` |
| `integration_pending` through `delivered` | exact R1 source tuple | exact approved IR tuple | exact verified B tuple |

`source_freeze_before_review=true` therefore means the exact source identity
exists and was frozen before the IR artifact. `final_review_approved=true`
means the exact IR identity resolves and approves `S`.
`decision_binding_complete=true` means the exact externally observed `B`
identity satisfies `R1-BINDING-SHAPE`. The booleans cannot be true in isolation.

### R2 repair and escalation truth

Let `N(r)` be the complete normal-state row for `r`. The only allowed
`repair_return_state` values are:

- `design_pending`
- `writer_release_pending`
- `source_freeze_pending`
- `change_review_pending`
- `integration_pending`

The owning failure maps exactly:

| Failed contract | `repair_return_state` |
| --- | --- |
| Design/schema/owner contract before writer release | `design_pending` |
| Writer release/cardinality/collision | `writer_release_pending` |
| Implementation, formatter/static, source-freeze commit, source delta | `source_freeze_pending` |
| Source review, reviewed tuple, review finding | `change_review_pending` |
| Decision-binding shape, integration consumer, closeout | `integration_pending` |

Special-state truth is:

| Special state | WR | SF | RV | DB | CU | routing | implementation/review/freeze+review | formatter+static | planned work |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `repair_pending` with `r` | `N(r).WR` | `N(r).SF` | `N(r).RV` | F | F | `pending` | `N(r)` values | F | F |
| `escalation_pending` with `r` | `N(r).WR` | `N(r).SF` | `N(r).RV` | F | F | `blocked` | `N(r)` values | F | F |

Exact preservation/reset semantics:

1. Entering `repair_pending` records one allowed `r`.
2. Writer-release, source-freeze, source identity, review approval, review
   identity, and the first three schedule booleans equal `N(r)` exactly.
3. Decision-binding identity and boolean reset to `null`/false.
4. Closeout resets to false.
5. Formatter/static active records reset to the exact pending records below;
   the schedule pass boolean resets to false.
6. Planned work resets to false.
7. A `repair_pending` successor is exactly `r` or
   `escalation_pending` with the same `r`.
8. Returning to `r` resets `repair_return_state` to `null` and requires every
   field to equal `N(r)`. If `N(r)` requires formatter/static pass, new valid
   pass records are mandatory.
9. `escalation_pending` preserves the same `r` and the same preserved/reset
   fields. Its only same-context exit is `repair_pending` with that same `r`
   after an owner decision. Changed intent starts a new context/logical key.
10. Neither special state can yield a ready boundary.

Stable special-state errors:

- `completion_authority:repair_return_state_missing`
- `completion_authority:repair_return_state_not_allowed:<state>`
- `completion_authority:repair_return_state_mismatch:<expected>:<actual>`
- `completion_authority:repair_preservation_mismatch:<field>`
- `completion_authority:repair_reset_mismatch:<field>`
- `completion_authority:escalation_routing_gate_mismatch`
- `completion_authority:special_state_ready_forbidden`
- `completion_authority:normal_state_repair_return_not_null:<state>`
- `completion_authority:topology_state_fact_mismatch:<state>:<field>`
- `completion_authority:schedule_state_fact_mismatch:<state>:<field>`
- `completion_authority:identity_presence_mismatch:<state>:<field>`

### R2 formatter/static event schema

`formatter_static_events` is always an ordered array of exactly two current
records:

```json
[
  {
    "schema": "agent-canon.formatter-static-event.v1",
    "record_id": "formatter-static:canonical_formatter",
    "ordinal": 1,
    "check_kind": "canonical_formatter",
    "status": "pending",
    "owner": "<source_binding.component_manager>",
    "source_event_ref": null,
    "artifact_path": null,
    "artifact_sha256": null,
    "artifact_blob": null
  },
  {
    "schema": "agent-canon.formatter-static-event.v1",
    "record_id": "formatter-static:selected_non_python_static",
    "ordinal": 2,
    "check_kind": "selected_non_python_static",
    "status": "pending",
    "owner": "<source_binding.component_manager>",
    "source_event_ref": null,
    "artifact_path": null,
    "artifact_sha256": null,
    "artifact_blob": null
  }
]
```

Exact predicates:

1. The array length is two.
2. Record order, `record_id`, `ordinal`, and `check_kind` equal the literals
   above. IDs and kinds are unique.
3. Allowed status values are `pending`, `pass`, `fail`,
   `deferred_by_user`, and `not_applicable`.
4. `owner` equals the aggregate component manager. A non-empty different owner
   fails.
5. For `pending`, all source/artifact fields are `null`.
6. For `pass` or `fail`, `source_event_ref` resolves to one canonical
   `validation` event with the same run/context, owner, check kind, and outcome.
   `artifact_path` is a repo-relative POSIX path; the file exists;
   `artifact_sha256` is its 64-character lowercase SHA256; and
   `artifact_blob` is the 40-character lowercase Git blob hash of those bytes.
7. For `deferred_by_user`, `source_event_ref` resolves to one canonical
   `deferral` event with exact outcome `deferred_by_user`; all artifact fields
   are `null`.
8. For `not_applicable`, `source_event_ref` resolves to one canonical
   `decision` event proving profile exclusion; all artifact fields are `null`.
9. `formatter_and_static_checks_pass` is true if and only if both ordered
   records are valid and both statuses are exactly `pass`.
10. `deferred_by_user`, `not_applicable`, `pending`, or `fail` never implies
    pass.

Stable formatter/static errors:

- `formatter_static:record_count`
- `formatter_static:record_order:<ordinal>`
- `formatter_static:duplicate_record_id:<record_id>`
- `formatter_static:duplicate_check_kind:<check_kind>`
- `formatter_static:field_missing:<check_kind>:<field>`
- `formatter_static:field_type:<check_kind>:<field>`
- `formatter_static:status_invalid:<check_kind>:<status>`
- `formatter_static:owner_mismatch:<check_kind>`
- `formatter_static:source_event_mismatch:<check_kind>`
- `formatter_static:artifact_required:<check_kind>`
- `formatter_static:artifact_forbidden:<check_kind>`
- `formatter_static:artifact_path_invalid:<check_kind>`
- `formatter_static:artifact_sha256_mismatch:<check_kind>`
- `formatter_static:artifact_blob_mismatch:<check_kind>`
- `formatter_static:schedule_equivalence_mismatch`

### R2 descendant-disposition schema

`descendant_disposition` has exactly these required keys:

```json
{
  "schema": "agent-canon.descendant-disposition.v1",
  "status": "none",
  "release": "not_applicable",
  "retained": "not_applicable",
  "members": []
}
```

Allowed values:

- `status`: `none`, `active`, or `settled`
- `release`: `not_applicable`, `none`, `some`, or `all`
- `retained`: `not_applicable`, `none`, `some`, or `all`
- `members`: an ordered array of exact records:

```json
{
  "descendant_id": "<stable descendant id>",
  "owner": "<canonical descendant event owner>",
  "disposition": "pending",
  "evidence_event_ref": null
}
```

Member predicates:

1. Members are sorted by unsigned UTF-8 bytes of `descendant_id`.
2. IDs are unique.
3. `disposition` is `pending`, `released`, or
   `retained_for_descendant`.
4. `owner` exactly equals the owner of the canonical descendant source event.
5. `pending` requires `evidence_event_ref=null`.
6. A terminal disposition requires a unique canonical event reference whose
   descendant ID, owner, and outcome match the member.

Aggregate predicates:

1. Empty members require
   `status=none`, `release=not_applicable`, and
   `retained=not_applicable`.
2. Any pending member requires `status=active`.
3. No pending member and at least one member require `status=settled`.
4. For non-empty members, `release` is `none`, `some`, or `all` according to
   the exact count of `released` members.
5. For non-empty members, `retained` is `none`, `some`, or `all` according to
   the exact count of `retained_for_descendant` members.
6. States before `writer_released` require the empty `none` object.
7. `writer_released` through `integration_pending` allow any internally valid
   object.
8. `publication_ready` and `delivered` allow only `none` or `settled`; an
   active descendant forbids closeout.
9. Special states use the allowed class for `repair_return_state`, but
   closeout remains false.

Stable descendant errors:

- `descendant_disposition:missing_key:<key>`
- `descendant_disposition:field_type:<key>`
- `descendant_disposition:field_value:<key>:<value>`
- `descendant_disposition:member_field_missing:<descendant_id>:<field>`
- `descendant_disposition:member_order`
- `descendant_disposition:duplicate_member:<descendant_id>`
- `descendant_disposition:owner_mismatch:<descendant_id>`
- `descendant_disposition:evidence_required:<descendant_id>`
- `descendant_disposition:evidence_forbidden:<descendant_id>`
- `descendant_disposition:evidence_mismatch:<descendant_id>`
- `descendant_disposition:status_aggregate_mismatch`
- `descendant_disposition:release_aggregate_mismatch`
- `descendant_disposition:retained_aggregate_mismatch`
- `descendant_disposition:state_mismatch:<state>`
- `descendant_disposition:active_closeout_forbidden`

### D5 complete non-self-referential publication DAG

The ordered interface schema becomes
`agent-canon.ordered-integration-interface.v3`. The version change is required
because R1 makes the canonical byte contract and direct-parent shape normative.
No compatibility wrapper or alternate interface is introduced.

| Node | Owner | Path/object | Required fields, hashes, and non-self-reference |
| --- | --- | --- | --- |
| `D` v3 design | `detailed_designer` | this successor path in a design-only commit | External readback supplies `D.commit`, `D.tree`, file blob, and file SHA256. This file contains none of those values. |
| `DR` independent design approval | `detailed_design_reviewer` | `w2_detailed_design_recheck_decision_<D-short>.md` | Contains exact D path/commit/tree/blob/SHA, decision `APPROVE`, and reviewer separation. It contains no hash/blob of its own bytes. |
| `S` source freeze | W2 implementation writer | Git commit/tree descending from `D` | Contains source/docs/tests/headers but not an ordered-interface update. External fields are base commit/tree, S commit/tree, canonical delta schema/digest, and mechanically derived paths. |
| `IR` independent implementation review | separate `change_reviewer` | `w2_implementation_review_<S-short>.md` | Contains S commit/tree, exact canonical reviewed diff digest, decision `APPROVE`, findings disposition, and reviewer separation. It contains no hash/blob of its own bytes. |
| `B` decision-binding commit | parent/integrator | one-parent commit | `parent(B)==S`; the canonical S→B delta has exactly the canonical interface path, both modes `100644`, old blob `0d72364dc37db1d0241d40444dbca15ea4cb95ec`, new blob equal to B’s interface bytes, and no other tree delta. The interface contains D/DR/S/IR only and contains no B identity. |
| `A_B` post-binding authority revision | component manager | canonical run ledger after B exists | Records B commit/tree/parent, canonical S→B digest and one-path array, interface path/blob/SHA, and transition `integration_pending`. It does not require its own Git identity. |
| `CR` external closeout receipt | verifier/auditor | run-local `closeout_gate.md` after B and `A_B` | Records the externally supplied B tuple, interface identity, selected authority revision, and integration-consumer result. It does not hash its own bytes. |
| Integration consumer | `task_close` verifier | checkout plus external `decision_binding_commit` | Recomputes every tuple and unlocks only at exact `publication_ready`; it does not trust interface or closeout success fields. |

The interface top-level shape is:

```json
{
  "schema": "agent-canon.ordered-integration-interface.v3",
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
    "delta_schema": "agent-canon.git-tree-delta.v1",
    "diff_sha256": "<canonical source delta SHA256>",
    "changed_paths": ["<mechanically derived ordered paths>"],
    "source_freeze_before_review": true
  },
  "implementation_review": {
    "path": "<IR path>",
    "sha256": "<IR SHA256>",
    "blob": "<IR blob>",
    "decision": "APPROVE",
    "reviewed_source_commit": "<S>",
    "reviewed_source_tree": "<S tree>",
    "reviewed_diff_sha256": "<same canonical source delta SHA256>"
  },
  "decision": {
    "state": "change_review_approved",
    "decision_source": "implementation_review"
  },
  "topology": {
    "schema": "agent-canon.control-topology-reference.v1",
    "authority_event_id": "<selected aggregate event id>",
    "authority_revision": 1,
    "authority_logical_key": {
      "run_id": "convergence-w2-gates-completion-20260716",
      "context_id": "<context id>",
      "authority": "completion_authority"
    },
    "snapshot_identity": "sha256:<ledger snapshot digest>",
    "projection_state": "change_review_approved"
  }
}
```

The interface omits `integration_ready`, B commit/tree/parent/diff, its own
path blob/SHA, and all other containing-commit identity. Its topology is a
fingerprint-bound reference to the selected authority event at
`change_review_approved`. The consumer reconstructs and validates the complete
R2 topology from that event; the interface does not copy success booleans.
Post-binding truth exists only in `A_B` and external Git readback.

The exact integration signature remains:

```python
def ordered_integration_decision_consumer(
    workspace: Path,
    report_dir: Path,
    decision_binding_commit: str,
) -> dict[str, object]:
    ...
```

Exact verifier algorithm:

1. Resolve externally supplied `B` and require exactly one parent.
2. Resolve interface `source_freeze.commit` as `S` and require
   `parent(B) == S`.
3. Recompute the canonical `S.tree→B.tree` serialization and require exactly
   one changed path, the full canonical interface path, old/new mode `100644`,
   old blob `0d72364dc37db1d0241d40444dbca15ea4cb95ec`, new blob equal to the
   interface bytes in B, and an otherwise identical tree.
4. Compare the recomputed S→B digest/path array with `A_B` and the external
   closeout receipt.
5. Resolve and hash D and require exact interface D path/commit/tree/blob/SHA.
6. Resolve DR bytes from its path, compare external DR SHA/blob, verify exact D
   tuple and `APPROVE`, and reject DR self-identity fields.
7. Resolve base and S, recompute the canonical base→S delta, require exact
   source digest/path array, require the interface path absent, and require the
   stale interface mode/blob unchanged in S.
8. Resolve IR bytes, compare external IR SHA/blob, verify exact S
   commit/tree/diff digest and `APPROVE`, and reject IR self-identity fields.
9. Reject any interface field that names B, B tree, B delta digest, interface
   blob/SHA, or another identity derived from its own containing commit/bytes.
10. Resolve the canonical authority head. Require its pre-binding projection to
    match the interface at `change_review_approved`, then require a later
    `A_B` revision at `integration_pending` with exact B identity.
11. Recompute all coverage, group, topology, formatter/static, descendant,
    repair, and boundary predicates from `L`; never consume a stored pass.
12. Return ready only when the selected state is `publication_ready`, no typed
    errors remain, and every R1-R3 predicate passes.

Additional publication failures:

- `ordered_integration:decision_commit_missing`
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
- `ordered_integration:pre_binding_topology_mismatch`
- `ordered_integration:post_binding_authority_missing`
- `ordered_integration:post_binding_identity_mismatch`

## Rejected Alternatives

The D1 choice still uses hard constraints only; no weighted score is used.

| Alternative | Ledger sole authority | Atomic state | Deterministic unique head | No second state machine | Result |
| --- | --- | --- | --- | --- | --- |
| Fine-grained typed authority events for owner, clauses, schedule, repair, topology, and publication | Pass | Fail without a transaction/batch layer | Fail without another coordinator | Fail when that coordinator is added | Rejected |
| One full-snapshot `completion_authority` aggregate event on `publication_state` | Pass | Pass | Pass through revision/supersession | Pass | Selected |
| External canonical state JSON referenced by a ledger pointer | Fail because the JSON becomes another authority | Pass | Pass | Fail | Rejected |

R1 rejected alternatives:

- Hashing `git diff`, `git diff-tree`, patch text, or tool stdout is rejected
  because quoting, headers, rename detection, config, version, and trailing
  newline behavior are not the source contract.
- Hashing a hand-written path list is rejected because it can diverge from the
  tree.
- Allowing ancestry instead of `parent(B)==S` is rejected because it admits
  unreviewed intermediate source.
- Allowing any second B path is rejected because it permits post-review source,
  test, doc, or header mutation.

R2 rejected alternatives:

- “True from state X onward” without repair/escalation rows is rejected.
- Non-empty text lists/objects for formatter or descendants are rejected.
- Treating `deferred_by_user` or `not_applicable` as pass is rejected.
- Keeping review or decision-binding booleans after a source-affecting repair
  without returning to the owning gate is rejected.

R3 rejected alternatives:

- A prose-only owner/consumer list without exact header kind and relative path
  is rejected.
- A durable edge to a dated run-local report is rejected.
- Adding every body-only navigation reference as a direct graph edge is
  rejected; direct edges follow the selected behavior/header dependency, while
  indirect readers depend through their canonical projection owner.

## Abstract Design Frame

### Replaceable responsibility unit

R1-R3, D1-D5, and F1-F6 form one replaceable
**completion-authority responsibility unit**:

1. append and resolve one canonical aggregate authority head from `L`;
2. derive every coverage, gate, topology, repair, formatter/static,
   descendant, and publication fact;
3. validate per-member correspondence and cross-member equality;
4. bind source review to one canonical base→S tree delta;
5. permit one exact interface-only direct-parent S→B delta;
6. enforce non-self-referential design/review/source/binding publication; and
7. keep owner docs, projections, checkers, tests, and dependency headers
   bidirectionally traceable.

The unit is replaceable only by another implementation preserving the exact
schemas, signatures, byte serialization, truth tables, typed failures,
publication DAG, dependency pairs, and public-oracle behavior.

### Authority flow

1. `work_log.py` reconstructs `L` and resolves one aggregate head.
2. `workflow_monitor.py` is an append adapter, not a state machine.
3. `report_artifact_checks.py` computes `P=f(L)`, observes Git trees, verifies
   R1-R3, and derives boundaries.
4. `task_close.py` supplies external B and consumes recomputed results.
5. `waterfall_gate_check.py` verifies current review targets before source work.
6. Canonical docs own schema/state/review/dependency rules; templates, tools,
   interfaces, and reports are consumers or projections.

### Invariants

- One selected aggregate revision supplies every non-Git recomputation input.
- Git source/binding facts come only from canonical object readback and the R1
  serializer.
- Stored views are projection-only and fingerprint-bound.
- Missing, duplicate, stale, forked, mismatched, or hand-mutated facts fail
  closed.
- Group validity requires both member correspondence and exact seven-field
  equality.
- `source_freeze_before_review` is exactly true only with a valid source tuple
  frozen before IR.
- `parent(B)==S`, B changes exactly the canonical interface path, and B is
  identical to S outside that path.
- No artifact hashes its own bytes or requires its own containing Git identity.
- Durable canon has no dependency edge to run-local reports.
- OOP, SOLID, formatter, tests, Python, CI, and graph execution do not become
  pass by prose.

### Non-goals

- No source, test, owner-doc, template, hook, interface, or checker edit in this
  design commit.
- No new database, external state service, second ledger, worktree,
  compatibility wrapper, alternate interface, dynamic graph, or hand-written
  pass artifact.
- No change to W1 resource production, GPU selection, unrelated failure
  taxonomy, or unrelated review families.

## Implementation Source Packet

### Bound predecessor and review identities

- Source predecessor commit:
  `80e63c4134058204e243c6140522d9e3671f9de6`
- Source predecessor tree:
  `5174b0dc1426e6afe8db78ba5f43a2320e79feef`
- v2 design commit:
  `1413d1ef6d51e588da05d4e8ff72b6b971b97d88`
- v2 design tree:
  `1470319d781430f94afb02885768ae9d4535b7c8`
- v2 design parent:
  `996b90d2915e9eab7cd384ab6d1b1b45bb6ae179`
- v2 design path:
  `reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v2.md`
- v2 design blob:
  `e201f07c5de65e5bfa3a3ca89a38d0c5c041f211`
- v2 design SHA256:
  `ba388e290371695732f26991a889a203ff720eee7aa74a64e2b7defbf0788e49`
- v2 independent recheck path:
  `/mnt/l/workspace/agent-canon-convergence-w2-final-writer-owned/reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_1413d1ef.md`
- v2 recheck SHA256:
  `6f9fd4e90cda7bc64aefbc810528de02303d4d1e19a13aba7bf4f9c6a98fec19`
- v2 recheck blob:
  `82aebadf86dc34408f4dcec92d15700e44623878`
- Ordered-interface predecessor mode:
  `100644`
- Ordered-interface predecessor blob:
  `0d72364dc37db1d0241d40444dbca15ea4cb95ec`

The supplied review decision is `REVISE` with exactly R1-R3 fix-now design
gaps. It records D2/D3 and F1/F2 as design-ready. This v3 artifact preserves
those decisions and changes no unrelated contract.

This artifact intentionally contains no identity for the commit/tree/blob/SHA
that will contain it. Those identities are returned only by external readback.

### Mandatory read-before-edit order

1. This v3 artifact in full.
2. The bound v2 recheck and v2 design above.
3. `agents/COMMUNICATION_PROTOCOL.md` CompletionCoverage schema owner.
4. `agents/canonical/CODEX_WORKFLOW.md` state/branch owner.
5. `documents/REVIEW_PROCESS.md` review lifecycle owner.
6. `documents/dependency-manifest-design.md` bidirectional/cycle rules.
7. `work_log.py`, `workflow_monitor.py`, `report_artifact_checks.py`,
   `task_close.py`, and `waterfall_gate_check.py`.
8. The exact selected projections, checkers, headers, interface, and tests in
   the Side-Effect Map.

### Implementation boundary

Implementation remains blocked until an independent reviewer approves this
exact v3 artifact. The implementation source freeze `S` includes all approved
owner docs, projections, implementation, headers, and tests. The ordered
interface is excluded from `S` and changes only in the later direct-parent
decision-binding commit `B`.

## Design Side-Effect Map

| Path | Exact future change | R1-R3 trace | Review/validation gate |
| --- | --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Add exact authority topology v2, formatter/static records, descendant records, source/review/binding identity fields, and typed errors. | R2; D1/D3 | Schema-owner and document-flow review |
| `agents/canonical/CODEX_WORKFLOW.md` | Add the complete normal/special truth tables, repair mapping, branch value, and transition rules. | R2; D2 | Workflow-owner review |
| `documents/REVIEW_PROCESS.md` | Add canonical tree-delta review identity, direct-parent interface-only binding, no-self-hash lifecycle, post-binding authority revision, and exact R3 downstream headers. | R1, R3; D5 | Review-policy and dependency review |
| `agents/workflows/implementation-waterfall-workflow.md` | Gate D approval, source freeze, IR, exact B shape, post-binding authority, and closeout in order. | R1-R3 | Workflow review |
| `agents/templates/design_review.md` | Require exact D tuple, reviewer separation, approval, and no self identity. | R3; D5 | Template review |
| `agents/templates/change_review.md` | Require S commit/tree, canonical diff schema/SHA, changed paths, reviewer separation, and no self identity. | R1, R3 | Template review |
| `agents/templates/final_review.md` | Verify D→DR→S→IR→B→A_B and R1-R3 acceptance. | R1-R3 | Template/final review |
| `agents/templates/closeout_gate.md` | Record external B/interface observation and selected post-binding authority without self-hashing the receipt. | R1, R3 | Closeout template review |
| `.codex/agents/ship_reviewer.toml` | Require R1-BINDING-SHAPE, latest review tuple, and post-binding authority evidence. | R1, R3 | Runtime alignment review |
| `tools/agent_tools/work_log.py` | Validate aggregate topology v2, truth tables, repair semantics, formatter/static and descendant records, and unique head. | R2; D1-D3 | Public ledger tests |
| `tools/agent_tools/workflow_monitor.py` | Preserve all structured fields and reject flattening/synthesized success. | R2; D1/D3 | Public monitor tests |
| `tools/agent_tools/report_artifact_checks.py` | Implement the exact R1 serializer/observer, R2 predicates, pure projection, and full ordered integration verifier. | R1-R2; F1-F5 | Code review and public negatives |
| `tools/agent_tools/task_close.py` | Supply external B, invoke authority and integration consumers, expose typed failures, and unlock only on recomputation. | R1-R3 | Public closeout tests |
| `tools/agent_tools/waterfall_gate_check.py` | Verify exact current D/DR and S/IR review targets and approval. | R1, R3 | Public gate tests |
| `tools/agent_tools/evaluate_agent_run.py` | Evaluate refreshed exact change/final review identities, not stale artifact presence. | R3 | Evaluation tests |
| `tools/agent_tools/agent_team.py` | Materialize REVIEW_PROCESS and exact review templates in selected role packets. | R3 | Runtime alignment/template tests |
| `tools/agent_tools/check_convention_compliance.py` | Enforce new review-policy markers and selected dependency edges. | R3 | Convention tests |
| `tools/agent_tools/tool_drift.py` | Enforce the already-declared REVIEW_PROCESS reverse dependency and new selected direct pairs. | R3 | Drift tests |
| ordered interface path | In B only, write v3 D/DR/S/IR projection; omit B/self identity and stored success. | R1, R2; D5 | Independent artifact review |
| `tests/agent_tools/test_work_log.py` | Public authority, truth-table, repair, formatter, descendant, branch, and group negatives. | R2; D1-D3/F5 | Test/oracle review |
| `tests/agent_tools/test_workflow_monitor.py` | Structured round-trip and no synthesized success. | R2; D1/D3/F5 | Test/oracle review |
| `tests/agent_tools/test_task_start_and_close.py` | Public R1 integration negatives, R2 topology negatives, hand mutation, freeze false, group mismatches, and pending honesty. | R1-R2; F1-F5 | Test/oracle review |
| `tests/agent_tools/test_waterfall_gate_check.py` | Exact stale/missing/mismatched design and implementation review tuple negatives. | R1, R3; D5/F5 | Test/oracle review |
| `tests/agent_tools/test_agent_team_templates.py` | Review/closeout template field rendering. | R3 | Template test review |
| `tests/agent_tools/test_evaluate_agent_run.py` | Latest review tuple and post-fix refresh behavior. | R3 | Evaluation test review |
| `tests/agent_tools/test_check_convention_compliance.py` | REVIEW_PROCESS markers and exact dependency-pair enforcement. | R3 | Convention test review |
| `tests/agent_tools/test_check_agent_runtime_alignment.py` | REVIEW_PROCESS role packet and ship reviewer alignment. | R3 | Runtime alignment review |

### R1 side-effect acceptance trace

The implementation in `report_artifact_checks.py`, its public consumers, the
ordered interface, and their tests must each encode all of these predicates:

- canonical base→S and S→B bytes use
  `agent-canon.git-tree-delta.v1`;
- `source_freeze.changed_paths` is mechanically decoded from those bytes;
- IR reviewed digest equals the source-freeze digest;
- `B` has exactly one parent and `parent(B)==S`;
- B’s path array is exactly the one canonical interface path;
- old/new mode is `100644`;
- old blob is `0d72364dc37db1d0241d40444dbca15ea4cb95ec`;
- new blob equals B’s interface bytes;
- B’s tree is identical to S outside that path;
- the external observation digest/path array matches recomputation.

### R3 exact durable dependency-header closure

`documents/REVIEW_PROCESS.md` must carry these exact owner-side edges, and each
consumer must carry the matching exact reverse:

| Owner-side line in `documents/REVIEW_PROCESS.md` | Exact consumer reverse line |
| --- | --- |
| `downstream design ../agents/templates/design_review.md exact detailed-design review identity projection` | `upstream design ../../documents/REVIEW_PROCESS.md exact detailed-design review identity policy` |
| `downstream design ../agents/templates/change_review.md exact source-review identity projection` | `upstream design ../../documents/REVIEW_PROCESS.md exact source-review identity policy` |
| `downstream design ../agents/templates/final_review.md final publication-chain review projection` | `upstream design ../../documents/REVIEW_PROCESS.md final publication-chain review policy` |
| `downstream design ../agents/templates/closeout_gate.md external decision-binding receipt projection` | `upstream design ../../documents/REVIEW_PROCESS.md external decision-binding receipt policy` |
| `downstream design ../agents/workflows/implementation-waterfall-workflow.md review and publication stage ordering` | `upstream design ../../documents/REVIEW_PROCESS.md review and publication stage policy` |
| `downstream implementation ../tools/agent_tools/waterfall_gate_check.py verifies current review target identity` | `upstream design ../../documents/REVIEW_PROCESS.md current review target identity policy` |
| `downstream implementation ../tools/agent_tools/report_artifact_checks.py verifies review and publication identities` | `upstream design ../../documents/REVIEW_PROCESS.md review and publication identity policy` |
| `downstream implementation ../tools/agent_tools/task_close.py consumes verified review and decision-binding evidence` | `upstream design ../../documents/REVIEW_PROCESS.md closeout review and binding policy` |
| `downstream implementation ../tools/agent_tools/evaluate_agent_run.py evaluates refreshed review artifacts` | `upstream design ../../documents/REVIEW_PROCESS.md refreshed review artifact policy` |
| `downstream implementation ../tools/agent_tools/agent_team.py materializes review role document packets` | `upstream design ../../documents/REVIEW_PROCESS.md review role document packet policy` |
| `downstream implementation ../tools/agent_tools/check_convention_compliance.py validates review-policy markers and wiring` | `upstream design ../../documents/REVIEW_PROCESS.md review-policy marker contract` |
| `downstream implementation ../tools/agent_tools/tool_drift.py validates review-policy dependency drift` | `upstream design ../../documents/REVIEW_PROCESS.md closeout validation policy` |
| `downstream implementation ../.codex/agents/ship_reviewer.toml final review and closeout runtime projection` | `upstream design ../../documents/REVIEW_PROCESS.md final review and closeout policy` |
| `downstream design ./algorithm-implementation-boundary.md algorithm equation/spec alignment review` | `upstream design ./REVIEW_PROCESS.md review gate for equation/spec alignment` |

The final two reverse lines already exist and therefore require matching owner
edges, not duplicate consumer lines. The algorithm-boundary owner edge already
exists and remains one exact pair.

Static enumeration disposition:

- `agent_team.py`, `evaluate_agent_run.py`, and
  `check_convention_compliance.py` are direct selected consumers because they
  read, materialize, evaluate, or mechanically validate REVIEW_PROCESS-owned
  review semantics.
- `ship_reviewer.toml` and `tool_drift.py` are direct reverse consumers because
  their current dependency headers already declare REVIEW_PROCESS upstream.
- Tests depend on their implementation/checker/template owner with
  `upstream implementation` or `upstream design`; they do not add a redundant
  direct REVIEW_PROCESS edge unless they themselves implement policy.
- Skills, internal routines, reader maps, runtime-profile projections, and
  body-only “Core References” mentions remain indirect navigation consumers
  unless their implementation behavior is selected above.
- `documents/runtime-profiles-and-check-matrix.json` remains the upstream
  taxonomy owner for validation-failure slugs. R3 does not reverse that
  authority.
- No durable dependency header may name
  `reports/agents/convergence-w2-gates-completion-20260716/*`.

## Design-to-Implementation Trace

| Slice | ADF derivation | Paths | Clauses | Required gate |
| --- | --- | --- | --- | --- |
| S1 Canonical authority/state owner | One full authority snapshot and exact state truth | `COMMUNICATION_PROTOCOL.md`, `CODEX_WORKFLOW.md` | R2, D1-D3 | Canonical owner review |
| S2 Canonical review/dependency owner | One review lifecycle and exact reverse graph | `REVIEW_PROCESS.md`, dependency headers | R3, D4-D5 | Review-policy/dependency review |
| S3 Ledger append/resolver | Select one valid aggregate head | `work_log.py`, `workflow_monitor.py` | R2, D1-D3 | Public ledger/monitor tests |
| S4 Canonical Git delta observer | Bind exact base→S and S→B bytes | `report_artifact_checks.py` | R1, D5, F4 | Code review and public integration negatives |
| S5 Pure projection/topology | Recompute all gates, repair, formatter, descendants | `report_artifact_checks.py` | R2, F1-F3 | Code review and public closeout negatives |
| S6 Review/closeout consumers | Verify exact current tuple and external B | `waterfall_gate_check.py`, `task_close.py`, `evaluate_agent_run.py` | R1-R3, D5 | Public gate/closeout tests |
| S7 Templates/runtime packets | Project owner policy without becoming authority | review/closeout templates, `agent_team.py`, ship reviewer | R3, D4 | Template/runtime alignment review |
| S8 Header/checker closure | Enforce every direct durable pair | `check_convention_compliance.py`, `tool_drift.py`, tests | R3, D4/F6 | Dependency/header checks |
| S9 Public oracle set | Reject every named mutation at public boundaries | selected test paths | R1-R3, F5 | Independent test/oracle review |
| S10 Source freeze `S` | Freeze S1-S9 together, excluding interface | one source commit/tree | R1-R3, D1-D5, F1-F6 | External source tuple readback |
| S11 Independent IR | Approve exact S canonical delta | external IR artifact | R1, D5 | Independent `APPROVE` |
| S12 Decision binding `B` | Direct-parent interface-only delta | ordered interface in one commit | R1, D5 | External B readback and integration consumer |
| S13 Post-binding/closeout | Record B after it exists and recompute readiness | aggregate revision and external receipt | R1-R2, D5/F5-F6 | Auditor/verifier |

Every implementation slice must cite this section and its clause IDs. A missing
schema field, byte rule, truth-table cell, error identity, edge pair, public
oracle, or publication field returns to detailed design review.

## Exact Acceptance Predicates

### D1

`D1=pass` if and only if:

1. `COMMUNICATION_PROTOCOL.md` owns the exact aggregate schema;
2. one full aggregate revision supplies every non-Git projection input;
3. one logical key/head is selected with the exact revision/supersession rules;
4. missing, duplicate, forked, transition, source-binding, writer, and topology
   mismatches use stable typed errors;
5. public signatures match this design; and
6. no public consumer accepts stored or caller-owned success authority.

### D2

`D2=pass` if and only if every listed owner, schema, constant, topology,
interface, and test consumer uses
`convergence_w2_gate_completion_authority`; the stale value appears only in a
negative fixture; and generic branch guards remain generic.

### D3

`D3=pass` if and only if every group first passes exact per-member source-event
correspondence and then every resolved event exactly equals the deterministic
baseline on all seven fields, including ordered evidence equality.

### D4

`D4=pass` if and only if:

1. both canonical schema/state owner docs and REVIEW_PROCESS are edited before
   projections;
2. all Side-Effect Map consumers are updated or explicitly rejected by
   independent review with evidence;
3. every R3 owner-side edge and consumer reverse line exists once with the
   exact kind and relative path;
4. the pre-existing ship-reviewer/tool-drift reverse declarations gain matching
   owner edges and the existing algorithm pair remains exact;
5. template/checker/test reverse consumers remain bidirectionally complete; and
6. no durable header names a run-local report.

### D5

`D5=pass` if and only if:

1. DR independently approves exact D;
2. S descends from D and the canonical base→S observation exactly equals
   `source_freeze.diff_sha256` and `changed_paths`;
3. S leaves the exact interface path at mode `100644` and blob
   `0d72364dc37db1d0241d40444dbca15ea4cb95ec`;
4. IR independently approves exact S commit/tree and the same canonical diff
   digest;
5. B has exactly one parent and `parent(B)==S`;
6. the canonical S→B delta contains exactly the full interface path, both modes
   `100644`, the exact old blob, a new blob equal to B’s interface bytes, and no
   other tree difference;
7. the interface binds D/DR/S/IR but contains no B/self identity or stored
   integration success;
8. a later authority revision and external receipt record and verify B after it
   exists; and
9. the integration consumer repeats every predicate and reaches
   `publication_ready` only after recomputation.

### F1

`F1=pass` if and only if `L` is sole authority, every stored view is
fingerprint-bound projection-only data, and hand-written gate/topology/success
mutations are ignored or rejected.

### F2

`F2=pass` if and only if owner, responsibility, outcome, and evidence are taken
from one distinct canonical event per member, never inferred from group-shared
fields.

### F3

`F3=pass` if and only if:

- every normal and special state matches the exact R2 tables;
- `source_freeze_before_review=true` has the exact R1 source identity;
- topology schema/order/run/context/observation identities match;
- repair/escalation preservation and resets match exactly; and
- formatter/static and descendant objects satisfy their exact schemas.

### F4

`F4=pass` if and only if the complete D→DR→S→IR→B→A_B→CR chain is
non-self-referential and B satisfies every direct-parent, one-path,
mode/blob/digest, and outside-tree-equality predicate.

### F5 public typed negative-test plan

Tests start from writer-generated temporary fixtures and exercise public
work-log, monitor, waterfall-gate, and task-close boundaries. They do not call
a private helper as the sole oracle and do not create closeout pass artifacts.

| Negative case | Public boundary | Required typed result |
| --- | --- | --- |
| Hand-written coverage/gate/boundary/topology success mutation | `completion_coverage_consumer` through `task_close.py` | recomputed false result or fingerprint mismatch |
| Missing/duplicate/forked authority | work-log resolver through public consumer | exact `completion_authority:*` error |
| Member missing/duplicate/mismatch | public projection/closeout | exact `group_member:*` error |
| `source_freeze_before_review=false` at/after `source_frozen` | public closeout | `completion_authority:topology_state_fact_mismatch:<state>:source_freeze_before_review` |
| Topology field missing or exact order mutated | resolver/public closeout | schema error or `topology_state_fact_mismatch` |
| Non-direct B parent | ordered integration through `task_close.py` | `ordered_integration:decision_parent_not_source` |
| B has multiple parents | ordered integration through `task_close.py` | `ordered_integration:decision_parent_count_mismatch` |
| Extra B path | ordered integration through `task_close.py` | `ordered_integration:decision_extra_path:<path>` |
| Wrong B path set | ordered integration through `task_close.py` | `ordered_integration:decision_path_set_mismatch` |
| B interface mode changed | ordered integration through `task_close.py` | `ordered_integration:decision_interface_mode_mismatch` |
| B old/new blob mismatch | ordered integration through `task_close.py` | exact old/new blob mismatch error |
| B diff hash mismatch | ordered integration through `task_close.py` | `ordered_integration:decision_diff_sha256_mismatch` |
| Source `changed_paths` hand mutation | ordered integration/public closeout | `source_freeze:changed_paths_mismatch` |
| Source diff digest hand mutation | ordered integration/public closeout | `source_freeze:diff_sha256_mismatch` |
| IR reviewed digest mismatch | ordered integration/public closeout | `implementation_review:reviewed_diff_sha256_mismatch` |
| Any normal-state fact flipped | resolver/public closeout | `completion_authority:topology_state_fact_mismatch` or schedule equivalent |
| Missing/invalid `repair_return_state` | resolver/public closeout | exact repair-return error |
| Repair preserved fact changed | resolver/public closeout | `completion_authority:repair_preservation_mismatch:<field>` |
| Repair reset fact retained | resolver/public closeout | `completion_authority:repair_reset_mismatch:<field>` |
| Formatter record missing/duplicate/reordered | resolver/public closeout | exact `formatter_static:*` structural error |
| Formatter status/owner/event/artifact mismatch | resolver/public closeout | exact `formatter_static:*` field error |
| Formatter boolean true without two pass records | resolver/public closeout | `formatter_static:schedule_equivalence_mismatch` |
| Descendant key/type/enum missing | resolver/public closeout | exact `descendant_disposition:*` schema error |
| Descendant member duplicate/order/evidence mismatch | resolver/public closeout | exact member/evidence error |
| Descendant aggregate status/release/retained mismatch | resolver/public closeout | exact aggregate mismatch error |
| Active descendant at publication/closeout | public closeout | `descendant_disposition:active_closeout_forbidden` |
| Interface self-identity attempt | ordered integration through `task_close.py` | `ordered_integration:interface_self_identity_forbidden` |
| Stale/missing D or IR review tuple | waterfall/ordered integration | exact review identity or approval error |

Validation status for this design successor:

- `oop_readability=pending`
- `solid_evidence=pending`
- `formatter=pending`
- `targeted_tests=pending`
- `python_execution=deferred_by_user`
- `ci=deferred_by_user`
- `dynamic_graph=deferred_by_user`
- `dependency_graph_execution=deferred_by_user`
- `implementation_authorization=blocked_until_independent_v3_design_approval`

No formatter, OOP/SOLID checker, Python, test, CI, or graph result is promoted
to pass by this prose. Real evidence is produced only by the owning
consolidated validation route after implementation exists.

### F6

`F6=pass` if and only if:

1. the implementation is bound to the exact predecessor/v2-review source
   packet above;
2. every source/doc/template/checker/test/interface impact is listed in the
   Side-Effect Map;
3. every slice traces to the ADF, clauses, owner, and gate;
4. every R3 direct edge has one exact reverse; and
5. the final source freeze, independent review, B readback, post-binding
   authority, and closeout receipt are externally observable without
   self-reference.
