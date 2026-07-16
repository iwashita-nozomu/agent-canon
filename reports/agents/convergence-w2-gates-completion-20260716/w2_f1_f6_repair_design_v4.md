# W2 F1-F6 Repair Design v4

## Reader Map

- Purpose: close the four findings in the independent recheck of the v3 design:
  external B selection authority, same-run changed-intent lifecycle, canonical
  formatter/descendant evidence-event encoding, and the missing
  convention-consistency checker dependency edge.
- Audience: canonical owner editors, the W2 implementation writer,
  independent design/change/final reviewers, and the parent/W3 integration
  owner.
- Reader order: Request Clauses → Owner Surfaces → Normative Incorporation →
  Selected Architecture → Rejected Alternatives → Abstract Design Frame →
  Implementation Source Packet → Design Side-Effect Map →
  Design-to-Implementation Trace → Exact Acceptance Predicates.
- Artifact relation: this file is an append-only successor to
  `w2_f1_f6_repair_design_v3.md`. It normatively incorporates every unaffected
  v3 contract and replaces only the sections listed under Normative
  Incorporation.
- First artifact: the frozen publication-authority tuple. It answers which
  reviewed B, source S, checkout HEAD, target ref, and integration result the
  verifier is authorized to inspect.
- Structure contract:
  - `structure_kind=document`
  - `document_unit=run-local detailed-design successor`
  - `document_split_decision=split:four independently reviewed contract gaps require an append-only successor while v3 remains historical evidence`
  - `structure_visual_plan=table:authority tuples, intent history, event schemas, mode predicates, and dependency pairs require exact field comparison`
  - `structure_source_map=v3 design plus supplied v3 REVISE artifact to V3-R1 through V3-R4 sections`
  - `structure_oop_contract=one replaceable completion-authority and publication-selection responsibility unit`
  - `discourse_relations=not_required`
  - `prose_graph_execution=not_run_by_user_constraint`
  - `structure_invalid_interpretations_recorded=yes`
- Dependency classification: this run-local artifact carries no durable
  dependency-manifest header. Durable canon must not point to this file.
- Invalid interpretations:
  - this artifact is not implementation authorization;
  - `decision_binding_commit` is no longer a caller-selected verifier input;
  - owner signature below is a canonical ledger owner attestation, not a new
    cryptographic PKI or secret-key subsystem;
  - an intent change never creates a second logical key in the same run;
  - canonical evidence-event hashes exclude their own hash field;
  - this artifact does not contain its own commit, tree, blob, or SHA256.

## Request Clauses

- `V4-P0-PUBLICATION-SELECTION`: make one canonical owner-signed and frozen
  publication tuple the sole authority for B, S, checkout HEAD, integration
  target/ref, merge/cherry-pick target, and integration result.
- `V4-P0-TOCTOU`: define exact before/after authority, HEAD, tree, status, and
  ref rereads so stale, moved, retargeted, or foreign identities fail closed.
- `V4-P1-INTENT-LIFECYCLE`: preserve one logical key per run through one
  immutable aggregate identity, monotone aggregate revision and intent version,
  exact intent fingerprint, and superseded intent history.
- `V4-P1-CANONICAL-EVIDENCE-EVENT`: define one exact evidence-event schema and
  serializer for formatter/static and descendant consumers, including owner,
  producer, source, order, hash, status, and disposition equality.
- `V4-R3-CONVENTION-CONSISTENCY`: add
  `tools/check_convention_consistency.py` as a direct
  `documents/REVIEW_PROCESS.md` consumer with exact forward/reverse headers,
  owner paths, test path, documentation path, and call edge.
- `PRESERVE-V3`: retain v3 canonical Git tree-delta bytes, exact B tree shape,
  topology truth tables, repair/reset rules, branch reason, group equality,
  non-self-reference, pending/deferred honesty, and all unaffected typed
  failures.
- `PRESERVE-D2-D3-F1-F2`: no regression to branch-reason, per-member equality,
  ledger sole authority, or member source-event authority.
- `DESIGN-ONLY-V4`: add only this v4 report artifact; do not edit source,
  Python, tests, formatter output, owner docs, hooks, or interface.

## Owner Surfaces

| Surface | Canonical responsibility | v4 decision |
| --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Aggregate/evidence event schemas, review packet identity fields, source correspondence | Owns immutable aggregate identity fields and `canonical_evidence_event.v1`. |
| `agents/canonical/CODEX_WORKFLOW.md` | State/intent transition policy, branch reason, integration stage | Owns same-key intent-version transitions and publication phase order. |
| `documents/REVIEW_PROCESS.md` | Review target identity, reviewer separation, post-fix refresh, publication review | Owns independent B review and integration-result review requirements plus R3 direct consumer edges. |
| `documents/dependency-manifest-design.md` | Edge kind, relative path, bidirectional consistency, cycle rules | Owns the added convention-consistency closure. |
| `tools/agent_tools/work_log.py` | Canonical event validation, append, snapshot, authority-head resolution | Sole durable run-ledger writer and validator for aggregate/evidence records. |
| `tools/agent_tools/workflow_monitor.py` | Structured monitor-to-ledger append boundary | Sole public structured ingress for `canonical_evidence_event`; it preserves the payload unchanged. |
| `tools/agent_tools/report_artifact_checks.py` | Pure projection, Git observations, publication selection and result verification | Derives B from the frozen tuple, performs HEAD/target/mode/TOCTOU checks, and validates evidence-event references. |
| `tools/agent_tools/task_close.py` | Public final closeout consumer and current Git observer | Calls the publication verifier without a B parameter and supplies current checkout readback only. |
| `tools/agent_tools/waterfall_gate_check.py` | Public staged review/preflight gate | Verifies binding-start and integration-start checkout predicates from canonical state. |
| `tools/check_convention_consistency.py` | Behavioral convention rule reader/checker | Directly consumes REVIEW_PROCESS rules and gains the exact owner/reverse edge. |
| `tools/run_comprehensive_review.sh` | Checker caller | Retains one invocation edge to the convention-consistency implementation. |
| `tools/README.md` | Shared tool navigation/documentation owner | Documents the checker responsibility and caller; it does not own review policy. |
| Run-local interface/reviews/receipts | Evidence/projection only | Bind owner facts but never select B, HEAD, target, intent, or success independently. |

## Normative Incorporation Of v3

The implementation packet is the union of v3 and v4. If a v4 replacement below
conflicts with v3, v4 wins. Otherwise v3 remains normative.

Retained unchanged:

- v3 `R1 canonical Git tree-delta serialization`, including SHA-1 object
  format, exact byte stream, complete hash range, strict path derivation,
  direct parent, interface-only S→B delta, exact modes/blobs, and outside-tree
  equality;
- v3 normal/special topology truth tables, repair preservation/reset semantics,
  exact branch reason, writer cardinality/collision, and topology order;
- v3 D2 and D3 contracts and typed group errors;
- v3 F1 and F2 sole-authority/member-source predicates;
- v3 non-self-referential D/DR/S/IR/interface constraints;
- v3 public negative-test and pending/deferred validation honesty;
- every v3 R3 dependency pair except the added direct consumer below.

Replaced:

1. v3 D1 logical-key selection is extended by the immutable aggregate and
   intent lifecycle in this artifact.
2. v3 sentence “Changed intent starts a new context/logical key” is deleted.
   The same run keeps one key and increments intent version.
3. v3 formatter/static and descendant source-event reference rules are
   replaced by `canonical_evidence_event.v1`.
4. v3 externally supplied `decision_binding_commit` verifier signature and
   D5 publication nodes are replaced by the frozen publication authority below.
5. v3 R3 closure gains the direct convention-consistency implementation,
   documentation, test, and caller edges below.

## Selected Architecture

### One immutable aggregate identity and one logical key

Each run has exactly one aggregate identity:

`aggregate_identity = completion-authority:<run_id>:<context_id>`.

`run_id`, `context_id`, `aggregate_identity`, and
`authority=completion_authority` are immutable from revision 1 onward.

The exact logical key is:

```json
{
  "run_id": "<run_id>",
  "context_id": "<context_id>",
  "aggregate_identity": "completion-authority:<run_id>:<context_id>",
  "authority": "completion_authority"
}
```

Every aggregate revision adds:

```json
{
  "aggregate_identity": "completion-authority:<run_id>:<context_id>",
  "revision": 1,
  "intent_version": 1,
  "intent_fingerprint": "<64 lowercase SHA256>",
  "current_intent": {
    "version": 1,
    "fingerprint": "<same SHA256>",
    "status": "current",
    "source_event_refs": ["<ordered request-clause event refs>"],
    "activated_at_revision": 1
  },
  "intent_history": [
    {
      "version": 1,
      "fingerprint": "<same SHA256>",
      "status": "current",
      "source_event_refs": ["<same ordered refs>"],
      "activated_at_revision": 1,
      "superseded_at_revision": null,
      "superseded_by_version": null
    }
  ]
}
```

The intent fingerprint serialization is
`agent-canon.intent-fingerprint.v1`:

```text
"agent-canon.intent-fingerprint.v1\0"
"run-id=" + <UTF-8 run_id> + "\0"
"aggregate-identity=" + <UTF-8 aggregate_identity> + "\0"
"intent-version=" + <16 lowercase ASCII hex> + "\0"
"clause-count=" + <16 lowercase ASCII hex> + "\0"
for each active request clause in user-contract row order:
  "clause\0"
  "clause-id-length=" + <16 lowercase ASCII hex> + "\0"
  "clause-id=" + <raw UTF-8 clause id> + "\0"
  "source-event-id-length=" + <16 lowercase ASCII hex> + "\0"
  "source-event-id=" + <raw UTF-8 event id> + "\0"
  "source-event-sha256=" + <64 lowercase ASCII hex> + "\0"
"end\0"
```

The fingerprint is SHA256 over the complete stream from the first byte through
the NUL in `end\0`, with no trailing byte. Source-event SHA256 values are the
SHA256 of the RFC-8785 canonical JSON UTF-8 bytes of the complete referenced
`request_clause` ledger event. No BOM or trailing newline is included.

Exact revision/intent rules:

1. Aggregate revision starts at 1 and increments by exactly one.
2. Same-intent state changes keep `intent_version` and
   `intent_fingerprint` unchanged.
3. Changed intent increments `intent_version` by exactly one and changes the
   fingerprint.
4. The prior current history row becomes `superseded`, sets
   `superseded_at_revision` to the new aggregate revision, and points
   `superseded_by_version` to the new version.
5. The new history row is appended once and is the only `current` row.
6. Earlier history rows are immutable.
7. `current_intent` exactly equals the one current history row.
8. Changed intent may transition from `escalation_pending` to
   `design_pending` in the same aggregate chain. It never creates a second
   context, aggregate identity, logical key, report directory, or ledger.
9. Evidence from an old fingerprint remains superseded history and cannot
   satisfy current gates.

Stable intent/identity failures:

- `completion_authority:aggregate_identity_missing`
- `completion_authority:aggregate_identity_mismatch`
- `completion_authority:duplicate_active_key`
- `completion_authority:forked_intent_key:<context_id>`
- `completion_authority:revision_regression:<previous>:<current>`
- `completion_authority:revision_gap:<previous>:<current>`
- `completion_authority:intent_version_regression:<previous>:<current>`
- `completion_authority:intent_version_gap:<previous>:<current>`
- `completion_authority:intent_fingerprint_mismatch`
- `completion_authority:intent_fingerprint_reused_for_changed_intent`
- `completion_authority:intent_history_mutated:<version>`
- `completion_authority:intent_history_multiple_current`
- `completion_authority:intent_history_current_missing`
- `completion_authority:intent_history_current_mismatch`
- `completion_authority:intent_source_refs_mismatch`

### Canonical evidence event

Formatter/static records and descendant members reference only
`agent-canon.canonical-evidence-event.v1`. No other event shape can satisfy
those consumers.

The payload field name in the ordinary ledger envelope and monitor passthrough
is exactly `canonical_evidence_event`.

The exact payload is:

```json
{
  "schema": "agent-canon.canonical-evidence-event.v1",
  "schema_version": 1,
  "event_id": "<canonical event id>",
  "event_key": {
    "run_id": "<run_id>",
    "aggregate_identity": "<immutable aggregate identity>",
    "intent_fingerprint": "<64 lowercase hex>",
    "event_kind": "formatter_static",
    "subject_id": "canonical_formatter"
  },
  "run_id": "<run_id>",
  "context_id": "<context_id>",
  "aggregate_identity": "<immutable aggregate identity>",
  "aggregate_revision": 1,
  "intent_version": 1,
  "intent_fingerprint": "<64 lowercase hex>",
  "source_snapshot": {
    "schema": "agent-canon.git-source-snapshot.v1",
    "snapshot_identity": "sha256:<source snapshot digest>",
    "commit": "<40 lowercase Git SHA-1>",
    "tree": "<40 lowercase Git SHA-1>"
  },
  "owner": "<completion_authority.source_binding.component_manager>",
  "producer_role": "component_manager",
  "producer_tool": "tools/agent_tools/workflow_monitor.py",
  "writer_tool": "tools/agent_tools/work_log.py",
  "source_tool_id": "<exact evidence producer id>",
  "event_kind": "formatter_static",
  "subject_id": "canonical_formatter",
  "status": "pass",
  "disposition": null,
  "ordered_evidence_refs": ["<ordered unique refs>"],
  "artifact": {
    "path": "<repo-relative POSIX path>",
    "sha256": "<64 lowercase hex>",
    "blob": "<40 lowercase Git blob>"
  },
  "timestamp_utc": "2026-07-16T00:00:00Z",
  "order_index": 1,
  "supersedes_event_id": null,
  "canonical_sha256": "<64 lowercase SHA256>"
}
```

Field/type rules:

1. `schema` and integer `schema_version=1` are exact.
2. `run_id`, `context_id`, aggregate identity, aggregate revision, intent
   version, and intent fingerprint bind the issuing aggregate revision.
3. `aggregate_revision` and `intent_version` are positive integers.
4. `source_snapshot.schema` is exact. Commit/tree are exact lowercase SHA-1 and
   resolve in the workspace object database. `snapshot_identity` is SHA256 of
   the exact bytes
   `agent-canon.git-source-snapshot.v1\0commit=<commit>\0tree=<tree>\0end\0`,
   including the final NUL and with no trailing byte.
5. `owner` is exactly the current component manager.
6. `producer_role` is exactly `component_manager`.
7. `producer_tool` is exactly
   `tools/agent_tools/workflow_monitor.py`.
8. `writer_tool` is exactly `tools/agent_tools/work_log.py`.
9. `ordered_evidence_refs` is non-empty, ordered, duplicate-free, and every
   reference resolves.
10. `timestamp_utc` is exact UTC second precision
    `YYYY-MM-DDTHH:MM:SSZ`.
11. `order_index` starts at 1 and increases by exactly one within an event key.
12. Revision `n>1` for one event key must supersede the exact prior head.
13. One event key has one unsuperseded head.

Event ID and key:

1. Compute lowercase SHA256 of UTF-8 `aggregate_identity`.
2. Compute lowercase SHA256 of UTF-8 `subject_id`.
3. The event ID is exactly:

`canonical-evidence:<aggregate_sha256>:<intent_version>:<event_kind>:<subject_sha256>:<order_index>`.

`intent_version` and `order_index` use base-10 ASCII with no sign and no
leading zero.

4. The event key is exactly
   `{run_id, aggregate_identity, intent_fingerprint, event_kind, subject_id}`.
5. A changed intent creates new evidence keys through the new fingerprint while
   retaining old keys as superseded history.

Semantic-kind/status table:

| Evidence use | Envelope `semantic_kind` | `event_kind` | `subject_id` | `status` | `disposition` | `source_tool_id` |
| --- | --- | --- | --- | --- | --- | --- |
| Canonical formatter pass/fail | `validation` | `formatter_static` | `canonical_formatter` | `pass` or `fail` | `null` | `tools/bin/agent-canon docs check` |
| Selected non-Python static pass/fail | `validation` | `formatter_static` | `selected_non_python_static` | `pass` or `fail` | `null` | exact profile-selected static tool ID |
| Formatter/static user deferral | `deferral` | `formatter_static` | either exact formatter subject | `deferred_by_user` | `null` | exact deferred tool ID |
| Formatter/static profile exclusion | `decision` | `formatter_static` | either exact formatter subject | `not_applicable` | `null` | `runtime-profile-selection` |
| Descendant pending | `responsibility_unit` | `descendant_disposition` | exact descendant ID | `active` | `pending` | `tools/agent_tools/workflow_monitor.py` |
| Descendant released | `responsibility_unit` | `descendant_disposition` | exact descendant ID | `settled` | `released` | `tools/agent_tools/workflow_monitor.py` |
| Descendant retained | `responsibility_unit` | `descendant_disposition` | exact descendant ID | `settled` | `retained_for_descendant` | `tools/agent_tools/workflow_monitor.py` |

The ordinary envelope `outcome` equals payload `status` for formatter events
and equals payload `disposition` for descendant events.

Artifact rules:

- Formatter `pass` and `fail` require the exact artifact object and byte/hash
  readback.
- Formatter `deferred_by_user` and `not_applicable` require `artifact=null`.
- Descendant events require `artifact=null`; their ordered evidence references
  identify source and terminal observations.

Source equality:

- A formatter/static event can satisfy the active records only when its source
  commit/tree equals the selected source S commit/tree.
- An active descendant event must match the current aggregate
  `authority_source_identity`.
- A settled descendant event may have an older aggregate revision, but must
  retain the current intent fingerprint, remain the selected event-key head,
  and resolve its source commit/tree.
- Any event from an old intent fingerprint is stale.

Canonical serialization/hash:

1. Form the complete payload object above without `canonical_sha256`.
2. Serialize it with RFC 8785 JSON Canonicalization Scheme.
3. Encode the canonical JSON as UTF-8 with no BOM or trailing newline.
4. `canonical_sha256` is lowercase SHA256 of those bytes.
5. The verifier reconstructs those bytes. Hashing the object including
   `canonical_sha256`, tool stdout, pretty JSON, or the containing ledger file
   is forbidden.

Writer/monitor ownership:

1. Actual formatter/static tools produce the evidence artifact.
2. The component manager constructs the structured payload and passes it
   through `workflow_monitor.py`.
3. `workflow_monitor.py` recognizes the exact passthrough field
   `canonical_evidence_event`, validates compact JSON structure, and preserves
   it unchanged.
4. `work_log.py` validates every field, event ID/key, ordering, semantic kind,
   source, and canonical hash before append.
5. No template, report checker, task-close consumer, or test writes a canonical
   event directly.

Formatter consumer equality:

`formatter_static_events` records gain
`source_event_sha256`. For each record, the consumer requires:

- `source_event_ref == canonical_evidence_event.event_id`;
- `source_event_sha256 == canonical_evidence_event.canonical_sha256`;
- record owner/status/artifact exactly equal the event;
- record `check_kind` maps exactly to event `subject_id`;
- event kind is `formatter_static`;
- run/context/aggregate identity/current intent fingerprint match;
- source commit/tree equal S;
- the event is the one selected unsuperseded head for its key.

Descendant consumer equality:

Each descendant member gains `evidence_event_sha256`. The consumer requires:

- `evidence_event_ref == canonical_evidence_event.event_id`;
- `evidence_event_sha256 == canonical_evidence_event.canonical_sha256`;
- `descendant_id == subject_id`;
- owner and disposition equal the event, and event status is exactly `active`
  for `pending` or `settled` for either terminal disposition;
- event kind is `descendant_disposition`;
- run/context/aggregate identity/current intent fingerprint match;
- event ordering/head and source rules pass.

Stable canonical-evidence failures:

- `canonical_evidence:missing:<event_id>`
- `canonical_evidence:schema_mismatch:<event_id>`
- `canonical_evidence:schema_version_mismatch:<event_id>`
- `canonical_evidence:event_id_mismatch:<event_id>`
- `canonical_evidence:event_key_mismatch:<event_id>`
- `canonical_evidence:foreign_run:<event_id>`
- `canonical_evidence:foreign_context:<event_id>`
- `canonical_evidence:foreign_aggregate:<event_id>`
- `canonical_evidence:stale_intent:<event_id>`
- `canonical_evidence:aggregate_revision_ahead:<event_id>`
- `canonical_evidence:source_snapshot_mismatch:<event_id>`
- `canonical_evidence:owner_mismatch:<event_id>`
- `canonical_evidence:producer_role_mismatch:<event_id>`
- `canonical_evidence:producer_tool_mismatch:<event_id>`
- `canonical_evidence:writer_tool_mismatch:<event_id>`
- `canonical_evidence:source_tool_mismatch:<event_id>`
- `canonical_evidence:event_kind_mismatch:<event_id>`
- `canonical_evidence:status_mismatch:<event_id>`
- `canonical_evidence:disposition_mismatch:<event_id>`
- `canonical_evidence:evidence_refs_invalid:<event_id>`
- `canonical_evidence:artifact_mismatch:<event_id>`
- `canonical_evidence:timestamp_invalid:<event_id>`
- `canonical_evidence:order_index_regression:<event_id>`
- `canonical_evidence:order_index_gap:<event_id>`
- `canonical_evidence:duplicate_head:<event_key>`
- `canonical_evidence:supersedes_mismatch:<event_id>`
- `canonical_evidence:hash_mismatch:<event_id>`
- `canonical_evidence:monitor_passthrough_missing:<event_id>`
- `canonical_evidence:record_reference_mismatch:<record_id>`

### Frozen publication authority

The sole selector of B is the `publication_authority` object in the selected
`completion_authority` head. No CLI argument, closeout field, interface field,
branch name, or current HEAD independently selects B.

The exact object is:

```json
{
  "schema": "agent-canon.publication-authority.v1",
  "publication_id": "w2-publication:<run_id>:<aggregate_identity>",
  "state": "selected",
  "selection_version": 1,
  "selection_owner": "<completion_authority.source_binding.parent>",
  "selection": {
    "aggregate_identity": "<aggregate identity>",
    "authority_revision": 1,
    "intent_version": 1,
    "intent_fingerprint": "<current fingerprint>",
    "source": {
      "commit": "<S>",
      "tree": "<S tree>",
      "diff_sha256": "<canonical base-to-S digest>"
    },
    "binding_start": {
      "head_commit": "<S>",
      "head_tree": "<S tree>",
      "tracked_tree_clean": true
    },
    "binding": {
      "commit": "<B>",
      "tree": "<B tree>",
      "parent": "<S>",
      "diff_sha256": "<canonical S-to-B digest>",
      "changed_paths": [
        "reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json"
      ],
      "interface_path": "reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json",
      "interface_blob": "<B interface blob>",
      "interface_sha256": "<B interface SHA256>"
    },
    "binding_review": {
      "path": "reports/agents/convergence-w2-gates-completion-20260716/w2_decision_binding_review_<first-12-hex-of-B>.md",
      "owner": "ship_reviewer",
      "sha256": "<review SHA256>",
      "blob": "<review blob>",
      "decision": "APPROVE",
      "reviewed_binding_commit": "<B>",
      "reviewed_binding_tree": "<B tree>",
      "reviewed_source_commit": "<S>",
      "reviewed_source_tree": "<S tree>",
      "reviewed_binding_diff_sha256": "<canonical S-to-B digest>",
      "reviewer_separate": true
    },
    "integration": {
      "mode": "direct_head",
      "target_ref": "refs/heads/<exact target branch>",
      "target_commit": "<T>",
      "target_tree": "<T tree>"
    }
  },
  "selection_sha256": "<64 lowercase SHA256>",
  "owner_signature": {
    "scheme": "agent-canon-ledger-owner-signature-v1",
    "owner": "<selection_owner>",
    "authority_event_id": "<containing aggregate event id>",
    "authority_revision": 1,
    "aggregate_identity": "<aggregate identity>",
    "intent_fingerprint": "<current fingerprint>",
    "selection_sha256": "<same selection SHA256>",
    "status": "frozen"
  },
  "result": null
}
```

The owner signature is structural:

- the aggregate envelope writer owner and `selection_owner` are equal to the
  canonical parent/integration owner;
- `work_log.py` validates the owner and frozen tuple hash before append;
- no external secret, key store, or alternate signer is introduced.

Selection hash:

1. Serialize the complete `selection` object with RFC 8785.
2. Encode UTF-8 with no BOM/trailing newline.
3. Hash those bytes with SHA256.
4. Later aggregate revisions repeat `selection`, `selection_sha256`, and
   owner-signature fields byte-for-byte.
5. Any mutation requires a new `selection_version`, a new independent B review,
   and a return to `integration_pending`; old selection remains superseded
   evidence.

The B review artifact is created after B and before selection freeze. It binds
B/S/tree/delta/interface identities and contains no hash/blob of its own bytes.
The publication tuple records its externally read SHA/blob.
Its owner is exactly `ship_reviewer`, and that role must be distinct from the
source writer, B writer, selection owner, and component manager. Its filename
suffix is exactly the first 12 lowercase hexadecimal characters of B.

The exact final result object is:

```json
{
  "selection_sha256": "<frozen selection hash>",
  "mode": "direct_head",
  "target_ref": "refs/heads/<same exact target branch>",
  "target_commit_before": "<T>",
  "target_tree_before": "<T tree>",
  "result_commit": "<R>",
  "result_tree": "<R tree>",
  "result_parents": ["<ordered parent commits>"],
  "integrated_binding_commit": "<B>",
  "cherry_pick_source_commit": null,
  "current_head": "<R>",
  "current_head_tree": "<R tree>",
  "tracked_tree_clean": true,
  "integrated_at_revision": 1,
  "result_sha256": "<64 lowercase SHA256>"
}
```

`result_sha256` is RFC-8785/SHA256 over the result object without
`result_sha256`. Later revisions repeat the result byte-for-byte.
The revision that first adds `result` is written by the same selection owner,
changes `publication_authority.state` from `selected` to `integrated`, and
leaves the frozen selection and owner signature unchanged.

### Exact integration-mode predicates

Common predicates:

1. S is the independently approved source tuple.
2. B is exactly the frozen selection B and has one parent S.
3. B satisfies every retained v3 R1 tree-delta predicate.
4. The B review independently approves exact B/S/delta/interface identities.
5. `target_ref` is a full `refs/heads/...` name; a short or symbolic alias is
   invalid.
6. At integration start, symbolic HEAD equals `target_ref`, the ref resolves to
   T, HEAD equals T, HEAD tree equals T tree, and tracked index/worktree diffs
   against HEAD are both empty.
7. At integration finish, symbolic HEAD still equals `target_ref`, the ref and
   HEAD resolve to result R, HEAD tree equals result tree, and tracked
   index/worktree diffs are empty.

Mode-specific predicates:

| Mode | Frozen target | Exact result |
| --- | --- | --- |
| `direct_head` | `T == S` and `T.tree == S.tree` | `R == B`; result parents exactly `[S]`; target ref and HEAD resolve B. |
| `merge` | S is an ancestor of T; B is not an ancestor of T; T’s interface mode/blob equal S’s pre-B interface mode/blob | R has exactly ordered parents `[T, B]`; T→R canonical delta is exactly the one interface path with B’s new blob; B and T are both direct parents. |
| `cherry_pick` | S is an ancestor of T; B is not an ancestor of T; T’s interface mode/blob equal S’s pre-B interface mode/blob | R has exactly one parent T; T→R canonical delta is exactly the one interface path with the same modes/old blob/new blob as S→B; result records `cherry_pick_source_commit=B`; B need not be an ancestor of R. |

No other mode is allowed. Merge/cherry-pick cannot integrate an unreviewed
source because S must already be an ancestor of the frozen target.
`integrated_binding_commit` is B for every mode.
`cherry_pick_source_commit` is B only for `cherry_pick` and is `null` for
`direct_head` and `merge`.

### Checkout and selection authority

The production signatures are:

```python
def publication_checkout_consumer(
    workspace: Path,
    report_dir: Path,
) -> dict[str, object]:
    ...

def ordered_integration_decision_consumer(
    workspace: Path,
    report_dir: Path,
) -> dict[str, object]:
    ...
```

Both derive the expected phase, S, B, target, mode, and result from the selected
aggregate head. Neither accepts a commit/ref/target override.

Allowed HEAD identities by phase:

| Derived phase | Exact allowed HEAD |
| --- | --- |
| `binding_start` | S only, with S tree and clean tracked state |
| `selection_review` | B only in the source/binding checkout, with B tree and clean tracked state |
| `integration_start` | frozen T only; direct mode therefore requires S |
| `integration_finish` / closeout | frozen result R only |

A later tracked commit, older valid B, foreign B, detached unrelated HEAD,
dirty tracked state, or ref resolving any other identity fails.

### TOCTOU-safe read algorithm

The verifier performs this exact sequence:

1. Read ledger snapshot `L1`, resolve authority head `A1`, and record event ID,
   revision, aggregate identity, intent fingerprint, snapshot identity,
   selection version/hash, and result hash.
2. Resolve symbolic HEAD, HEAD commit/tree, target ref commit/tree, tracked
   staged diff state, and tracked unstaged diff state as Git observation `G1`.
3. Resolve D/DR/S/IR/B/B-review/interface/target/result objects and verify all
   hashes, ancestry, parent order, and tree-delta predicates.
4. Read ledger snapshot again as `L2` and require the same authority event,
   revision, aggregate identity, intent fingerprint, snapshot identity,
   selection version/hash, and result hash.
5. Resolve symbolic HEAD, HEAD commit/tree, target ref commit/tree, and tracked
   staged/unstaged states again as `G2`.
6. Require `G2 == G1` field-for-field.
7. Re-run the final mode-specific equality/ancestry checks using `A2` and `G2`.
8. Return ready only if every check passes. No cached first-read decision is
   reused after the reread.

Stable publication-selection/TOCTOU failures:

- `publication_authority:missing`
- `publication_authority:multiple`
- `publication_authority:schema_mismatch`
- `publication_authority:owner_mismatch`
- `publication_authority:owner_signature_mismatch`
- `publication_authority:selection_hash_mismatch`
- `publication_authority:selection_mutated`
- `publication_authority:selection_version_regression`
- `publication_authority:intent_mismatch`
- `publication_authority:binding_review_missing`
- `publication_authority:binding_review_identity_mismatch`
- `publication_authority:binding_review_not_approved`
- `publication_authority:foreign_b`
- `publication_authority:stale_b`
- `publication_authority:source_mismatch`
- `publication_authority:binding_start_head_mismatch`
- `publication_authority:head_mismatch`
- `publication_authority:head_tree_mismatch`
- `publication_authority:tracked_tree_dirty`
- `publication_authority:target_ref_not_full`
- `publication_authority:target_ref_mismatch`
- `publication_authority:target_commit_mismatch`
- `publication_authority:target_tree_mismatch`
- `publication_authority:target_not_source_successor`
- `publication_authority:integration_mode_mismatch`
- `publication_authority:merge_parent_mismatch`
- `publication_authority:merge_delta_mismatch`
- `publication_authority:cherry_pick_parent_mismatch`
- `publication_authority:cherry_pick_source_mismatch`
- `publication_authority:cherry_pick_delta_mismatch`
- `publication_authority:result_identity_mismatch`
- `publication_authority:receipt_selection_mismatch`
- `publication_authority:authority_changed_during_verification`
- `publication_authority:head_changed_during_verification`
- `publication_authority:target_ref_moved_during_verification`
- `publication_authority:tracked_state_changed_during_verification`

### R3 convention-consistency direct consumer

The exact new durable pair is:

| Owner-side line in `documents/REVIEW_PROCESS.md` | Consumer reverse line |
| --- | --- |
| `downstream implementation ../tools/check_convention_consistency.py parses review-policy rules for convention contradiction checks` | `upstream design ../documents/REVIEW_PROCESS.md review-policy rule source` |

The path from `tools/check_convention_consistency.py` to the owner uses one
`..`, not two.

The complete owner/caller/test/document closure for this checker is:

| Owner/path | Exact edge/responsibility |
| --- | --- |
| `documents/REVIEW_PROCESS.md` | Canonical review-rule owner; downstream implementation edge above. |
| `tools/README.md` | Tool navigation owner; adds `downstream implementation ./check_convention_consistency.py convention consistency checker`. |
| `tools/check_convention_consistency.py` | Adds upstream REVIEW_PROCESS, retains `upstream design README.md`, adds `downstream implementation ./run_comprehensive_review.sh invokes checker`, and adds `downstream implementation ../tests/agent_tools/test_check_convention_compliance.py verifies convention consistency behavior and wiring`. |
| `tools/run_comprehensive_review.sh` | Adds `upstream implementation ./check_convention_consistency.py convention consistency check`; both parallel and sequential calls remain the same implementation edge. |
| `tests/agent_tools/test_check_convention_compliance.py` | Adds `upstream implementation ../../tools/check_convention_consistency.py convention consistency behavior under test`; tests direct REVIEW_PROCESS loading and header closure through the public script boundary. |
| `tools/agent_tools/check_convention_compliance.py` | Adds/retains marker checks for the exact pair and caller/test/doc closure. |

There is no duplicate owner:

- REVIEW_PROCESS owns review rules.
- `tools/README.md` owns navigation only.
- `check_convention_consistency.py` implements contradiction scanning.
- `run_comprehensive_review.sh` invokes it.
- the existing test path owns public behavior/header regression coverage.
- `check_convention_compliance.py` validates wiring but does not replace the
  behavioral checker.

No edge points to a run-local report.

## Rejected Alternatives

- Retaining `decision_binding_commit` as a public parameter is rejected because
  the caller can select an older valid B.
- Defining B as “current HEAD” without a frozen target/ref and mode is rejected
  because merge/cherry-pick integration has a different result commit.
- Trusting a branch name without frozen commit/tree is rejected because refs can
  move or be retargeted.
- Reading authority/HEAD/ref once is rejected because the decision is exposed
  to TOCTOU drift.
- Creating a new context/logical key for changed intent is rejected because the
  same append-only run would deterministically contain multiple keys.
- Rewriting old intent rows is rejected because history would cease to be
  append-only evidence.
- Leaving formatter/descendant event fields to arbitrary envelope extensions is
  rejected because consumers cannot distinguish foreign/stale events.
- A compatibility B override, test-only selector API, or alternate publication
  file is rejected.
- Treating `check_convention_consistency.py` as a body-only reader is rejected
  because it directly loads and parses REVIEW_PROCESS rules.

## Abstract Design Frame

### Replaceable responsibility unit

The unit remains one replaceable completion-authority responsibility:

1. preserve one immutable aggregate identity and one logical key;
2. advance aggregate revision and intent version monotonically;
3. append canonical evidence events with exact source/owner/order/hash;
4. derive formatter and descendant truth from selected event heads;
5. freeze one owner-attested publication selection;
6. verify reviewed B, source S, target/ref, checkout, integration mode/result,
   and TOCTOU rereads;
7. project completion from ledger/Git readback only; and
8. preserve exact durable owner/consumer dependency closure.

Replacing any implementation slice is valid only if these schemas, public
signatures, equality/ancestry predicates, typed errors, and public negative
oracles remain unchanged.

### Authority flow

1. `work_log.py` owns canonical aggregate/evidence append and selection.
2. `workflow_monitor.py` is the structured ingress.
3. `report_artifact_checks.py` reconstructs authority and Git facts.
4. `waterfall_gate_check.py` validates pre-integration checkout phases.
5. `task_close.py` invokes final verification without identity overrides.
6. REVIEW_PROCESS owns B review and result-review policy.
7. Dependency checkers validate all direct durable pairs.

### Invariants

- One run has one aggregate identity and one logical key.
- One current intent exists; old intents are immutable superseded history.
- Current formatter/descendant records reference exact canonical event heads.
- B comes only from a frozen owner-attested selection.
- B is independently reviewed before selection freeze.
- Binding starts at S; integration starts at frozen T; closeout HEAD is exact R.
- Ref, HEAD, tree, tracked state, and authority are read twice.
- Merge/cherry targets already contain S.
- No artifact hashes its own complete bytes or requires its own containing Git
  identity.
- Stored booleans and hand-written receipts do not override recomputation.

### Non-goals

- No source/Python/test/formatter/dynamic-graph execution or edit in v4.
- No cryptographic key infrastructure, compatibility selector, test-only API,
  second ledger, second logical key, alternate interface, or new persistence
  service.
- No change to retained v3 tree-delta bytes, D2/D3, F1/F2, or unrelated W1/GPU
  responsibilities.

## Implementation Source Packet

### Bound predecessor and review identities

- Source predecessor:
  `80e63c4134058204e243c6140522d9e3671f9de6`
- Source predecessor tree:
  `5174b0dc1426e6afe8db78ba5f43a2320e79feef`
- v3 design commit:
  `a2cebf5239d80b044453bed2e58f9fa7e988991d`
- v3 design tree:
  `09abe61f0af729789ab3e98f56a2843f79bb8169`
- v3 direct parent:
  `1413d1ef6d51e588da05d4e8ff72b6b971b97d88`
- v3 design path:
  `reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v3.md`
- v3 design SHA256:
  `08ac8de1e3bf823eaf11cf4c67a7bcf3b055a76100e98f0bf01bcfcff6c23139`
- v3 design blob:
  `e1fe14123356e2658672cab78ca7bebd6ef8bf50`
- v3 independent REVISE path:
  `/mnt/l/workspace/agent-canon-convergence-w2-final-writer-owned/reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_a2cebf52.md`
- v3 recheck SHA256:
  `63501c8ecd46a6fda38c79b0713c1688fc8e9ccdcad11f4196e923ff4a60854b`
- v3 recheck blob:
  `ea97339ed1cb515f5ee41b41b5eac0032aa0acda`

The review decision is `REVISE` with exactly four findings. It confirms no
regression in D2, D3, F1, F2, self-reference, compatibility, or test-only API
boundaries.

This v4 artifact intentionally omits its own containing commit/tree/blob/SHA.

### Mandatory read-before-edit order

1. This v4 artifact.
2. The bound v3 recheck and v3 design.
3. `COMMUNICATION_PROTOCOL.md`, `CODEX_WORKFLOW.md`,
   `REVIEW_PROCESS.md`, and dependency-manifest design.
4. `work_log.py`, `workflow_monitor.py`, `report_artifact_checks.py`,
   `task_close.py`, and `waterfall_gate_check.py`.
5. `tools/check_convention_consistency.py`,
   `tools/run_comprehensive_review.sh`, `tools/README.md`, and the selected
   convention test/checker paths.
6. Every retained v3 Side-Effect Map path.

### Implementation boundary

Implementation remains blocked until independent approval of this exact v4
artifact. Source freeze S includes all approved owner, implementation, header,
caller, documentation, and test changes except the later ordered-interface B
commit. B is independently reviewed before its publication selection is
frozen.

## Design Side-Effect Map

| Path | Exact future change | Finding | Gate |
| --- | --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Add aggregate identity/intent fields and canonical evidence-event schema/serializer. | V3-R2, V3-R3 | Schema-owner review |
| `agents/canonical/CODEX_WORKFLOW.md` | Replace new-key changed-intent route with same-key intent versioning; add publication phase and mode rules. | V3-R1, V3-R2 | Workflow-owner review |
| `documents/REVIEW_PROCESS.md` | Require independent B review, frozen publication selection/result review, and convention-consistency downstream edge. | V3-R1, V3-R4 | Review/dependency review |
| `documents/dependency-manifest-design.md` | No semantic change; apply existing exact bidirectional rules to the new pair/call closure. | V3-R4 | Dependency review |
| `tools/README.md` | Document convention-consistency checker owner/caller/test route and add downstream edge. | V3-R4 | Docs review |
| `tools/agent_tools/work_log.py` | Validate aggregate/intent history, canonical evidence payload/hash/order, publication tuple/signature/freeze. | V3-R1-R3 | Ledger tests/review |
| `tools/agent_tools/workflow_monitor.py` | Add exact `canonical_evidence_event` passthrough and public round trip. | V3-R3 | Monitor tests |
| `tools/agent_tools/report_artifact_checks.py` | Resolve B from publication authority; validate event references, integration modes, HEAD/target/result, and TOCTOU. | V3-R1-R3 | Public verifier tests |
| `tools/agent_tools/task_close.py` | Remove B parameter path; call no-override final consumer and expose typed failures. | V3-R1 | Public closeout tests |
| `tools/agent_tools/waterfall_gate_check.py` | Call no-override checkout consumer at binding/integration preflight. | V3-R1 | Public gate tests |
| `agents/templates/change_review.md` | Add canonical evidence/source snapshot fields and independent B review packet. | V3-R1, V3-R3 | Template review |
| `agents/templates/final_review.md` | Verify selection/result hashes, target/ref/mode, reread evidence, and current intent. | V3-R1-R3 | Final review |
| `agents/templates/closeout_gate.md` | Record selected authority/result identities only; no caller B override. | V3-R1 | Closeout review |
| `.codex/agents/ship_reviewer.toml` | Require canonical selection/result and TOCTOU evidence. | V3-R1 | Runtime alignment |
| `tools/check_convention_consistency.py` | Add REVIEW_PROCESS upstream and caller/test downstream headers; retain behavior. | V3-R4 | Checker review |
| `tools/run_comprehensive_review.sh` | Add reverse call edge; invocation remains canonical. | V3-R4 | Shell/checker review |
| `tools/agent_tools/check_convention_compliance.py` | Validate exact new owner/reverse/caller/test/doc edges and markers. | V3-R4 | Convention tests |
| `tools/agent_tools/tool_drift.py` | Include convention-consistency direct edge/caller in drift checks. | V3-R4 | Drift tests |
| `tests/agent_tools/test_work_log.py` | Same-key intent and canonical evidence/publication payload negatives. | V3-R1-R3 | Test-oracle review |
| `tests/agent_tools/test_workflow_monitor.py` | Canonical evidence passthrough round-trip and drop/schema negatives. | V3-R3 | Test-oracle review |
| `tests/agent_tools/test_task_start_and_close.py` | Older valid B, HEAD/B, dirty/later HEAD, moved target/ref, mode/result, TOCTOU negatives. | V3-R1 | Test-oracle review |
| `tests/agent_tools/test_waterfall_gate_check.py` | Binding/integration start HEAD/target mismatch negatives. | V3-R1 | Test-oracle review |
| `tests/agent_tools/test_check_convention_compliance.py` | Direct script behavior and exact dependency/caller/test/doc closure. | V3-R4 | Test-oracle review |
| ordered interface path | Retain v3 interface schema/tree shape; no B selector or result identity is added to its own bytes. | Preserve self-reference | Independent B review |

Every retained v3 Side-Effect Map path remains in scope.

### Exact dependency closure addition

Required forward/reverse lines:

- REVIEW_PROCESS:
  `downstream implementation ../tools/check_convention_consistency.py parses review-policy rules for convention contradiction checks`
- convention checker:
  `upstream design ../documents/REVIEW_PROCESS.md review-policy rule source`
- tools README:
  `downstream implementation ./check_convention_consistency.py convention consistency checker`
- convention checker retained reverse:
  `upstream design README.md shared automation index`
- convention checker caller edge:
  `downstream implementation ./run_comprehensive_review.sh invokes checker`
- caller reverse:
  `upstream implementation ./check_convention_consistency.py convention consistency check`
- convention checker test edge:
  `downstream implementation ../tests/agent_tools/test_check_convention_compliance.py verifies convention consistency behavior and wiring`
- test reverse:
  `upstream implementation ../../tools/check_convention_consistency.py convention consistency behavior under test`

No duplicate edge is added for the two existing shell call sites; they are two
calls under one implementation dependency.

## Design-to-Implementation Trace

| Slice | Responsibility derivation | Paths | Clauses | Gate |
| --- | --- | --- | --- | --- |
| S1 Aggregate/intent identity | One run, one key, monotone current intent | protocol/workflow owners, `work_log.py` | V4-P1 | Owner review + ledger tests |
| S2 Canonical evidence events | One typed evidence head per subject/key | protocol, monitor, work log, report checks | V4-P1 | Public round-trip/negative tests |
| S3 Publication selection | One reviewed B selected by frozen owner tuple | review/workflow owners, report checks | V4-P0 | Independent B review |
| S4 Checkout/target modes | Exact S/B/T/R equality and ancestry | report checks, waterfall, task close | V4-P0 | Public gate/closeout tests |
| S5 TOCTOU | Two authority and Git observation reads | report checks, task close | V4-P0 | Mutation/race negatives |
| S6 Convention checker edge | One policy owner, implementation, caller, doc, test | R3 paths | V4-R3 | Header/checker review |
| S7 Retained v3 implementation | Tree delta, topology, D2/D3/F1/F2 | all retained v3 paths | PRESERVE-V3 | Regression review |
| S8 Source freeze | Freeze S1-S7 source/docs/tests, excluding interface | S commit/tree | all | External tuple readback |
| S9 B and B review | Interface-only direct child and independent review | B/BR artifacts | V4-P0 | `APPROVE` |
| S10 Integration/result | Apply selected mode to frozen target and reread | publication result/closeout | V4-P0 | Auditor/verifier |

## Exact Acceptance Predicates

### Finding 1: external B selection authority

Pass if and only if:

1. one canonical `publication_authority.v1` object exists in the selected
   aggregate head;
2. selection owner equals canonical parent/integration owner;
3. owner signature and selection hash validate;
4. B and independent B review identities match exactly;
5. no verifier accepts a B/ref/target override;
6. binding start HEAD is S;
7. integration start HEAD/ref is frozen T;
8. closeout HEAD/ref/tree is exact result R;
9. direct/merge/cherry predicates match the selected mode;
10. closeout receipt and aggregate result bind the same selection hash/B; and
11. authority/Git rereads remain identical.

### Finding 2: changed-intent key lifecycle

Pass if and only if:

1. run/context/aggregate identity/logical key never change;
2. aggregate revision is consecutive;
3. same-intent revisions retain version/fingerprint;
4. changed intent increments version once and changes fingerprint;
5. old current history becomes immutable superseded history;
6. exactly one current history row equals `current_intent`;
7. no second key/context is appended in the run; and
8. old-intent evidence cannot satisfy current gates.

### Finding 3: canonical evidence event

Pass if and only if:

1. formatter and descendant consumers reference only exact
   `canonical_evidence_event.v1` heads;
2. schema/version/event ID/key/run/context/aggregate/revision/fingerprint/source
   owner/producer/kind/status/disposition/evidence/timestamp/order/hash all
   validate;
3. monitor passthrough and work-log append preserve the payload;
4. record/member fields exactly equal their referenced event;
5. foreign, stale, superseded, missing, out-of-order, or hash-mismatched events
   fail typed; and
6. no direct test/template write becomes canonical evidence.

### Finding 4: convention-consistency closure

Pass if and only if:

1. REVIEW_PROCESS and `tools/check_convention_consistency.py` contain the exact
   direct pair;
2. tools README/checker, checker/caller, and checker/test pairs are exact;
3. `check_convention_compliance.py` and `tool_drift.py` select the path;
4. the two shell call sites remain one call dependency;
5. no owner conflict or duplicate header edge exists; and
6. no durable edge targets a run-local report.

### Preserved D2/D3/F1/F2

- D2: the only positive branch reason remains
  `convergence_w2_gate_completion_authority`.
- D3: each member first resolves one canonical event and then exactly equals
  the baseline on all seven fields, including ordered evidence.
- F1: `L` plus canonical Git readback is sole authority; projections and
  receipts are fingerprint-bound and non-authoritative.
- F2: owner/responsibility/outcome/evidence come from each member’s own source
  event, never a group-shared inference.

### Preserved self-reference and interface shape

- D/DR/S/IR/B-review artifacts do not contain hashes of their own complete
  bytes.
- The ordered interface contains no B containing-commit/tree/blob/SHA selector.
- Publication selection/result are appended after their referenced Git objects
  exist.
- Canonical evidence hash excludes `canonical_sha256`.
- No compatibility interface or test-only selector API exists.

### Public negative-test plan

| Negative | Public boundary | Typed failure |
| --- | --- | --- |
| Older valid B substituted | task-close publication consumer | `publication_authority:stale_b` or `foreign_b` |
| B differs from frozen selection | final consumer | `publication_authority:foreign_b` |
| Binding-start HEAD not S | waterfall/public checkout consumer | `publication_authority:binding_start_head_mismatch` |
| Later tracked HEAD at closeout | task close | `publication_authority:head_mismatch` |
| HEAD tree differs | task close | `publication_authority:head_tree_mismatch` |
| Staged/unstaged tracked mutation | checkout/final consumer | `publication_authority:tracked_tree_dirty` |
| Short/foreign target ref | checkout/final consumer | `target_ref_not_full` or `target_ref_mismatch` |
| Target ref moved between reads | final consumer | `target_ref_moved_during_verification` |
| Authority revision/selection changed between reads | final consumer | `authority_changed_during_verification` |
| HEAD changed between reads | final consumer | `head_changed_during_verification` |
| Merge target does not contain S | final consumer | `target_not_source_successor` |
| Merge parent order/extra parent wrong | final consumer | `merge_parent_mismatch` |
| Merge tree adds another path | final consumer | `merge_delta_mismatch` |
| Cherry result parent/source/delta mismatch | final consumer | exact cherry-pick typed error |
| Receipt names another selection/B | closeout | `receipt_selection_mismatch` |
| Second logical key in same run | work-log resolver | `duplicate_active_key` or `forked_intent_key` |
| Revision regresses/skips | work-log resolver | exact revision regression/gap |
| Intent version regresses/skips | work-log resolver | exact intent-version error |
| History has two current rows | work-log resolver | `intent_history_multiple_current` |
| `current_intent` differs from history | work-log resolver | `intent_history_current_mismatch` |
| Old fingerprint event referenced | projection/closeout | `canonical_evidence:stale_intent` |
| Evidence event missing/foreign | monitor/work-log/public consumer | exact missing/foreign error |
| Evidence schema/version mismatch | monitor/work-log/public consumer | exact schema error |
| Event ID/key/hash mismatch | work-log/public consumer | exact ID/key/hash error |
| Source commit/tree stale | projection/closeout | `source_snapshot_mismatch` |
| Producer/owner/tool mismatch | work-log/public consumer | exact owner/producer error |
| Order regression/gap/duplicate head | work-log/public consumer | exact ordering/head error |
| Monitor drops payload | monitor round trip | `monitor_passthrough_missing` |
| Formatter/descendant record differs from event | projection/closeout | `record_reference_mismatch` |
| Convention checker missing direct edge | convention compliance/drift | exact dependency finding |
| Caller/test/doc reverse missing | convention compliance/drift | exact reverse-edge finding |

Positive public lifecycle cases:

- changed intent increments version/fingerprint on the same logical key and
  retains one current history row;
- direct mode freezes T=S and closes with HEAD/ref/result=B;
- merge and cherry modes accept only a frozen target containing S and exact
  mode-specific result structure;
- formatter and descendant payloads round-trip monitor→work log→consumer with
  exact hash/equality.

### Validation honesty

- `oop_readability=pending`
- `solid_evidence=pending`
- `formatter=pending`
- `targeted_tests=pending`
- `python_execution=deferred_by_user`
- `ci=deferred_by_user`
- `dynamic_graph=deferred_by_user`
- `dependency_graph_execution=deferred_by_user`
- `implementation_authorization=blocked_until_independent_v4_design_approval`

No source, Python, test, formatter, CI, or dynamic command is promoted to pass
by this design.
