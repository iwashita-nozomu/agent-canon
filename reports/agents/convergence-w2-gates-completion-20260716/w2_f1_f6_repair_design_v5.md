# W2 F1-F6 Repair Design v5

## Reader Map

This artifact is the append-only v5 design revision for the W2 completion
authority responsibility unit. It is design only. It does not authorize source,
test, owner-document, formatter, CI, or dynamic-graph changes.

Read this artifact in the following order:

1. `Request Clauses` fixes the four v5 review findings.
2. `Owner Surfaces` fixes the owner and consumer boundaries.
3. `Normative Incorporation Of v4` identifies retained and replaced contracts.
4. `Selected Architecture` defines the exact schemas, authority chain,
   transitions, CAS linearization, typed failures, and public signatures.
5. `Abstract Design Frame` states the replaceable responsibility unit.
6. `Implementation Source Packet` binds this design to its predecessor and
   independent review evidence.
7. `Design Side-Effect Map` and `Design-to-Implementation Trace` enumerate the
   future implementation surface without changing it.
8. `Exact Acceptance Predicates` is the implementation and independent-review
   oracle.

The implementation packet is the union of:

- `w2_f1_f6_repair_design_v3.md`;
- `w2_f1_f6_repair_design_v4.md`; and
- this v5 artifact.

When text conflicts, v5 replaces v4, and v4 replaces v3. All non-conflicting
v3/v4 clauses remain normative. In particular, v5 does not weaken D2, D3, F1,
F2, the canonical Git tree-delta contract, topology truth tables, dependency
closure, non-self-reference, or validation honesty.

This artifact deliberately contains no identity for its own containing commit,
tree, blob, or complete-file SHA256. Those identities are external readback
evidence only.

## Request Clauses

| Clause | Required closure |
| --- | --- |
| V5-P0-A | Split B authority into a pre-review owner-attested candidate, an independent immutable review receipt, and a post-APPROVE publication authority. |
| V5-P0-B | Linearize integration with an expected-old-OID compare-and-swap and bind completion to the actual post-CAS ref readback. |
| V5-P1-A | Replace duplicate-shaped current intent state with immutable revision rows and one current-row pointer. |
| V5-P1-B | Add a canonical formatter `pending` event and exact pending-to-terminal transition semantics. |
| PRESERVE | Preserve convention closure, D2/D3/F1/F2, all v3/v4 pass findings, non-self-reference, no compatibility selector, and no test-only API. |

## Owner Surfaces

| Surface | Exact ownership |
| --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Canonical ledger envelope, immutable intent revision, canonical evidence-event, and context visibility schemas. |
| `agents/canonical/CODEX_WORKFLOW.md` | Candidate creation/attestation owner, publication transaction, target tuple, branch reason, topology, integration mode, and CAS route. |
| `documents/REVIEW_PROCESS.md` | Independent candidate-review receipt policy, reviewer separation, approval semantics, templates, and durable review-consumer closure. |
| `documents/dependency-manifest-design.md` | Exact forward/reverse dependency-header grammar and closure rules. |
| `tools/agent_tools/work_log.py` | Canonical append, current-head selection, immutable history, event ordering, and structural owner attestation. |
| `tools/agent_tools/workflow_monitor.py` | Structured event ingress and byte-preserving canonical payload passthrough. |
| `tools/agent_tools/report_artifact_checks.py` | Read-only public authority, artifact, Git-object, tree-delta, pointer, and receipt verification. |
| `tools/agent_tools/publication_integrator.py` | Future single-purpose owner tool for result-object construction, expected-old-OID CAS, post-CAS readback, and generated integration receipt. |
| `tools/agent_tools/waterfall_gate_check.py` | Public pre-publication checkout and topology consumer. |
| `tools/agent_tools/task_close.py` | Public closeout consumer; recomputes completion and never selects B or a target. |
| `tools/check_convention_consistency.py` | Direct behavioral consumer of canonical review-policy rules. |
| `tools/agent_tools/check_convention_compliance.py` and `tools/agent_tools/tool_drift.py` | Durable dependency/header and selected-consumer consistency. |

No report artifact becomes an upstream owner of durable canon. Run-local
artifacts are evidence nodes only.

## Normative Incorporation Of v4

Retained unchanged:

- v3 R1 `agent-canon.git-tree-delta.v1`, including the exact byte range,
  ordering, encoding, terminal delimiter, path derivation, modes, old/new
  blobs, direct-parent predicate, interface-only path set, and outside-tree
  equality;
- exact ordered interface path
  `reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json`;
- v3 normal and exceptional topology truth tables, exact `freeze=true`, order,
  identity, writer cardinality, repair-return, escalation, and branch-reason
  predicates;
- canonical branch reason
  `convergence_w2_gate_completion_authority`;
- v3 D2 owner convergence and v3 D3 member-to-event then cross-member exact
  equality;
- F1 canonical-ledger sole authority and pure projection;
- F2 per-member owner/responsibility/outcome/evidence source correspondence;
- canonical aggregate `completion_authority` event as the sole selected head;
- all v3/v4 R3 convention-consistency owner/caller/test/document edges,
  including `tools/check_convention_consistency.py`;
- non-self-referential D/DR/S/IR/B/review/publication sequencing;
- no compatibility interface, caller-supplied B, fallback selection, or
  test-only production API;
- public typed negative oracles and pending/deferred validation honesty.

Replaced:

1. v4 `current_intent` and mutable `intent_history` rows are deleted and
   replaced by immutable `IntentRevisionRecord` rows plus one pointer.
2. v4 canonical evidence-event formatter rules are replaced by the tagged
   pending/terminal schema and current-event pointer rules below.
3. v4 monolithic `publication_authority` selection of an already reviewed B is
   split into candidate attestation, independent review receipt, and
   post-APPROVE publication authority.
4. v4 two-read readiness check is retained as preflight evidence but is not the
   integration linearization point. The exact CAS below is the only
   publication linearization point.
5. v4 publication result is extended with a generated
   `IntegrationCASReceipt` and exact post-CAS ref readback.

## Selected Architecture

### Immutable intent revisions and one current pointer

One run retains the exact v4 logical key:

```json
{
  "run_id": "<run_id>",
  "context_id": "<context_id>",
  "aggregate_identity": "completion-authority:<run_id>:<context_id>",
  "authority": "completion_authority"
}
```

`run_id`, `context_id`, `aggregate_identity`, and `authority` are immutable.
Changed intent never creates another logical key, context, ledger, or report
directory.

The aggregate contains exactly these intent fields:

```json
{
  "intent_revisions": [
    {
      "schema": "agent-canon.intent-revision-record.v1",
      "schema_version": 1,
      "intent_revision_id": "intent-revision:<aggregate-sha256>:1:<intent-fingerprint>",
      "aggregate_identity": "completion-authority:<run_id>:<context_id>",
      "version": 1,
      "fingerprint": "<64 lowercase SHA256>",
      "previous_intent_revision_id": null,
      "source_event_refs": ["<ordered request-clause event refs>"],
      "activated_at_aggregate_revision": 1,
      "canonical_sha256": "<64 lowercase SHA256>"
    }
  ],
  "current_intent_revision_id": "intent-revision:<aggregate-sha256>:1:<intent-fingerprint>"
}
```

No `current_intent`, intent-row `status`, `superseded_at_revision`,
`superseded_by_version`, duplicate top-level `intent_version`, or duplicate
top-level `intent_fingerprint` field is allowed.

The exact `IntentRevisionRecord` rules are:

1. `schema` and integer `schema_version=1` are exact.
2. `aggregate-sha256` is lowercase SHA256 of the UTF-8 bytes of
   `aggregate_identity`.
3. `version` is a positive integer. Its ID representation is base-10 ASCII
   without sign or leading zero.
4. `fingerprint` uses the retained v4
   `agent-canon.intent-fingerprint.v1` byte serialization and complete hash
   range.
5. `intent_revision_id` is exactly
   `intent-revision:<aggregate-sha256>:<version>:<fingerprint>`.
6. `previous_intent_revision_id` is `null` at version 1 and is the exact ID of
   the immediately preceding row for every later version.
7. `source_event_refs` is non-empty, ordered, duplicate-free, and every event
   resolves to the active request-clause event used by the fingerprint.
8. `activated_at_aggregate_revision` is the first aggregate revision that
   selects the row and is a positive integer.
9. Form the complete row without `canonical_sha256`, serialize with RFC 8785,
   encode UTF-8 with no BOM or trailing newline, and SHA256 those bytes.
10. `canonical_sha256` is that lowercase digest. A later aggregate snapshot
    repeats every prior row byte-for-byte.

The list and pointer rules are:

1. `intent_revisions` is append-only and ordered by `version`.
2. The first row has version 1. Each later row increments by exactly one.
3. Same-intent aggregate revisions leave the complete list and pointer
   byte-for-byte unchanged.
4. Changed intent appends exactly one new immutable row and advances
   `current_intent_revision_id` to that row.
5. The pointer equals the ID of the last row. The current intent is exactly
   that referenced row; no copied object participates in equality.
6. All rows before the pointer are superseded history by list order and pointer
   position. No historical row is mutated to express supersession.
7. A separate immutable transition event may explain the change, but it cannot
   mutate an intent row or create another current pointer.
8. Evidence consumers dereference the pointer, then compare the event
   `intent_version` and `intent_fingerprint` with that exact row.
9. Two selected aggregate heads for the same logical key, two pointer-bearing
   aggregate records at one revision, a second pointer field, or a forked
   intent list is a duplicate-current failure.

Stable intent failures:

- `completion_authority:aggregate_identity_missing`
- `completion_authority:aggregate_identity_mismatch`
- `completion_authority:duplicate_active_key`
- `completion_authority:forked_intent_key:<context_id>`
- `completion_authority:revision_regression:<previous>:<current>`
- `completion_authority:revision_gap:<previous>:<current>`
- `completion_authority:intent_revision_duplicate_id:<intent_revision_id>`
- `completion_authority:intent_current_pointer_missing`
- `completion_authority:intent_current_pointer_not_found:<intent_revision_id>`
- `completion_authority:intent_current_pointer_not_last`
- `completion_authority:intent_multiple_current_pointers`
- `completion_authority:intent_version_non_monotone:<previous>:<current>`
- `completion_authority:intent_version_gap:<previous>:<current>`
- `completion_authority:intent_previous_pointer_mismatch:<intent_revision_id>`
- `completion_authority:intent_fingerprint_mismatch:<intent_revision_id>`
- `completion_authority:intent_fingerprint_reused_for_changed_intent`
- `completion_authority:intent_source_refs_mismatch:<intent_revision_id>`
- `completion_authority:intent_revision_mutated:<intent_revision_id>`
- `completion_authority:intent_revision_hash_mismatch:<intent_revision_id>`

### Canonical evidence event with pending state

Formatter/static and descendant consumers continue to accept only
`agent-canon.canonical-evidence-event.v1`. The ledger payload field remains
exactly `canonical_evidence_event`.

The common event fields are:

```json
{
  "schema": "agent-canon.canonical-evidence-event.v1",
  "schema_version": 1,
  "event_id": "<canonical event id>",
  "event_key": {
    "run_id": "<run_id>",
    "aggregate_identity": "<immutable aggregate identity>",
    "aggregate_revision": 1,
    "intent_fingerprint": "<current intent fingerprint>",
    "event_kind": "formatter_static",
    "subject_id": "canonical_formatter"
  },
  "run_id": "<run_id>",
  "context_id": "<context_id>",
  "aggregate_identity": "<immutable aggregate identity>",
  "aggregate_revision": 1,
  "intent_revision_id": "<current intent revision ID>",
  "intent_version": 1,
  "intent_fingerprint": "<current intent fingerprint>",
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
  "source_tool_id": "<exact selected producer ID>",
  "event_kind": "formatter_static",
  "subject_id": "canonical_formatter",
  "status": "pending",
  "disposition": null,
  "ordered_evidence_refs": [],
  "timestamp_utc": "2026-07-16T00:00:00Z",
  "order_index": 1,
  "supersedes_event_id": null,
  "canonical_sha256": "<64 lowercase SHA256>"
}
```

The common-field rules from v4 remain, with these exact replacements:

1. `event_key` is exactly
   `{run_id, aggregate_identity, aggregate_revision, intent_fingerprint,
   event_kind, subject_id}`.
2. `event_id` is exactly
   `canonical-evidence:<aggregate-sha256>:<aggregate_revision>:<intent-version>:<event-kind>:<subject-sha256>:<order-index>`.
3. Numeric ID segments are base-10 ASCII without sign or leading zero.
4. The event's intent fields must equal the row selected by
   `current_intent_revision_id`.
5. `order_index` starts at 1 and increases by exactly one for one event key.
6. An event after the first names the exact preceding head in
   `supersedes_event_id`.
7. One event key has exactly one unsuperseded head.
8. Canonical hashing remains RFC-8785 JSON UTF-8 over the complete tagged event
   without `canonical_sha256`, with no BOM or trailing newline.

The formatter/static event is a tagged union.

| Status | Required fields | Forbidden fields | Transition |
| --- | --- | --- | --- |
| `pending` | common fields; `ordered_evidence_refs=[]`; `disposition=null` | `artifact`; `completed_at_utc` | initial only; may advance to `pass` or `fail` |
| `pass` | non-empty ordered evidence refs; exact `artifact`; exact `completed_at_utc`; `disposition=null` | none of the pending omissions | only from the current `pending` event for the same key |
| `fail` | non-empty ordered evidence refs; exact `artifact`; exact `completed_at_utc`; `disposition=null` | none of the pending omissions | only from the current `pending` event for the same key |
| `deferred_by_user` | exact deferral refs; `artifact` absent; `completed_at_utc`; `disposition=null` | terminal tool-result artifact | direct terminal event for a newly selected aggregate revision |
| `not_applicable` | exact profile-decision refs; `artifact` absent; `completed_at_utc`; `disposition=null` | terminal tool-result artifact | direct terminal event for a newly selected aggregate revision |

For `pass` and `fail`, `artifact` is exactly:

```json
{
  "path": "<repo-relative POSIX path>",
  "sha256": "<64 lowercase SHA256>",
  "blob": "<40 lowercase Git blob>"
}
```

`completed_at_utc` and the common `timestamp_utc` use exact UTC second
precision `YYYY-MM-DDTHH:MM:SSZ`. `timestamp_utc` is event issuance time;
`completed_at_utc` is terminal evidence completion time and cannot precede it.

Pending transition predicates:

1. A pending formatter record references one canonical pending event by exact
   ID and canonical hash.
2. The pending event may use the exact empty tuple `[]` for
   `ordered_evidence_refs`.
3. A later `pass` or `fail` is a new immutable event with the same event key,
   aggregate revision, current intent row, source snapshot, owner, producer,
   source tool, kind, and subject.
4. The terminal event has `order_index = pending.order_index + 1` and
   `supersedes_event_id = pending.event_id`.
5. The old pending event remains byte-for-byte history.
6. The consumer's current-event pointer advances to the terminal event.
7. `pass` or `fail` can never transition to `pending`.
8. A second pending event for the same key, pending-to-deferred,
   pending-to-not-applicable, terminal-to-terminal, or a skipped predecessor is
   invalid.
9. A later retry starts only under a new aggregate revision and therefore a
   new event key.

Exact formatter record variants:

```json
{
  "check_kind": "canonical_formatter",
  "status": "pending",
  "current_event_ref": "<pending event ID>",
  "current_event_sha256": "<pending event canonical SHA256>"
}
```

```json
{
  "check_kind": "canonical_formatter",
  "status": "pass",
  "current_event_ref": "<terminal event ID>",
  "current_event_sha256": "<terminal event canonical SHA256>",
  "artifact": {
    "path": "<same event artifact path>",
    "sha256": "<same event artifact SHA256>",
    "blob": "<same event artifact blob>"
  }
}
```

The `fail` record has the same terminal shape with `status=fail`.
`selected_non_python_static` uses the same schema and exact pointer/hash rules.
No non-empty-text fallback is allowed.

Descendant disposition retains the v4 status/disposition table and uses the
same common event schema. Each descendant record replaces a loose evidence
reference with:

```json
{
  "current_event_ref": "<selected descendant event ID>",
  "current_event_sha256": "<selected event canonical SHA256>"
}
```

The record's descendant ID, owner, state, API/dependency owner, responsibility
unit, outcome, disposition, ordered evidence refs, aggregate identity, intent
row, source identity, and all required descendant-disposition keys must exactly
equal the referenced selected event. The retained v3 R2 truth table and typed
errors remain normative.

Stable pending/pointer failures:

- `canonical_evidence:pending_event_missing:<subject_id>`
- `canonical_evidence:pending_event_duplicate:<event_key>`
- `canonical_evidence:pending_artifact_forbidden:<event_id>`
- `canonical_evidence:pending_completed_at_forbidden:<event_id>`
- `canonical_evidence:pending_evidence_refs_not_empty:<event_id>`
- `canonical_evidence:terminal_artifact_missing:<event_id>`
- `canonical_evidence:terminal_completed_at_missing:<event_id>`
- `canonical_evidence:terminal_evidence_refs_empty:<event_id>`
- `canonical_evidence:invalid_transition:<from>:<to>`
- `canonical_evidence:terminal_to_pending_forbidden:<event_id>`
- `canonical_evidence:current_pointer_missing:<record_id>`
- `canonical_evidence:current_pointer_not_found:<record_id>`
- `canonical_evidence:current_pointer_not_head:<record_id>`
- `canonical_evidence:current_pointer_hash_mismatch:<record_id>`
- `canonical_evidence:aggregate_revision_mismatch:<event_id>`
- `canonical_evidence:intent_revision_mismatch:<event_id>`

Every retained v4 canonical-evidence failure remains active.

### Pre-review InterfaceCandidateAttestation

The existence and identity of candidate B are authorized before review by one
immutable, owner-attested `InterfaceCandidateAttestation`. This attestation
does not approve publication or integration.

The canonical owner is exactly
`completion_authority.source_binding.parent`. The owner surface is exactly
`agents/canonical/CODEX_WORKFLOW.md#interface-candidate-authority`.

The exact object is:

```json
{
  "schema": "agent-canon.interface-candidate-attestation.v1",
  "schema_version": 1,
  "attestation_id": "interface-candidate:<aggregate-sha256>:1",
  "candidate_version": 1,
  "owner_identity": "<completion_authority.source_binding.parent>",
  "owner_surface": "agents/canonical/CODEX_WORKFLOW.md#interface-candidate-authority",
  "repository": {
    "repository_id": "agent-canon",
    "object_format": "sha1"
  },
  "aggregate_binding": {
    "aggregate_identity": "<immutable aggregate identity>",
    "authority_revision": 1,
    "current_intent_revision_id": "<current intent revision ID>",
    "intent_fingerprint": "<current intent fingerprint>"
  },
  "source": {
    "commit": "<S>",
    "tree": "<S tree>",
    "diff_sha256": "<canonical base-to-S digest>"
  },
  "candidate": {
    "commit": "<B>",
    "tree": "<B tree>",
    "parent": "<S>",
    "delta_serialization": "agent-canon.git-tree-delta.v1",
    "delta_sha256": "<canonical S-to-B digest>",
    "changed_paths": [
      "reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json"
    ],
    "interface_path": "reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json",
    "interface_mode": "<exact B tree mode>",
    "interface_blob": "<B interface blob>",
    "interface_sha256": "<B interface SHA256>"
  },
  "candidate_ref": {
    "refname": "refs/agent-canon/interface-candidates/<aggregate-sha256>/1",
    "object_id": "<B>",
    "creation_expected_old_oid": "0000000000000000000000000000000000000000",
    "immutable": true
  },
  "intended_integration_target": {
    "repository_id": "agent-canon",
    "route": "local_ref",
    "mode": "direct_head",
    "target_ref": "refs/heads/<exact target branch>",
    "expected_target_oid": "<G-attested>",
    "expected_target_tree": "<G-attested tree>",
    "remote_name": null,
    "pr_owner_api": null
  },
  "issued_at_utc": "2026-07-16T00:00:00Z",
  "nonce": "<64 lowercase hex>",
  "attestation_body_sha256": "<64 lowercase SHA256>",
  "owner_attestation": {
    "scheme": "agent-canon-ledger-owner-attestation-v1",
    "owner_identity": "<same owner identity>",
    "owner_surface": "agents/canonical/CODEX_WORKFLOW.md#interface-candidate-authority",
    "authority_event_id": "<containing aggregate event ID>",
    "authority_revision": 1,
    "attestation_body_sha256": "<same digest>",
    "status": "frozen"
  }
}
```

Exact attestation rules:

1. `attestation_id` uses the aggregate SHA256 and positive base-10
   `candidate_version` without leading zero.
2. The owner-only candidate producer starts from exact source S and the
   canonical ordered-interface bytes. It creates B, then creates the candidate
   ref with expected old OID equal to 40 zeroes. No public caller supplies B.
3. `parent(B) == S`.
4. B's tree delta from S is the retained canonical serialization and has the
   exact one-path set containing only the ordered interface.
5. B's tree is byte-identical to S outside that path. Modes, old/new blobs,
   path bytes, order, encoding, and terminal delimiter satisfy v3 R1.
6. `candidate_ref.refname` is the exact full ref for this aggregate/version.
   It resolves to B before append and on every later read.
7. The ref is immutable. A retry or changed target uses the next candidate
   version and a new ref. An existing candidate ref is never moved.
8. The intended target tuple records one route, mode, full target ref,
   expected target OID/tree, and route-specific owner fields. It is frozen
   before independent review.
9. `remote_name` is non-null only for `route=remote_ref`.
   `pr_owner_api` is non-null only for `route=pr_merge`.
10. `issued_at_utc` uses exact UTC second precision. `nonce` is 32 bytes
    represented by 64 lowercase hexadecimal characters and is unique within
    the aggregate.
11. `attestation_body_sha256` is SHA256 of RFC-8785 canonical UTF-8 bytes of
    the complete object from `schema` through `nonce`, excluding
    `attestation_body_sha256` and `owner_attestation`, with no BOM or trailing
    newline.
12. `owner_attestation` is structural owner evidence validated by
    `work_log.py`; it is not a caller-provided assertion and introduces no
    external secret-key service.
13. The selected aggregate head contains exactly one
    `current_interface_candidate_attestation_id` pointer. Consumers resolve B
    only through that pointer and the immutable candidate ref.

The exact public resolver is:

```python
def resolve_current_interface_candidate(
    workspace: Path,
    report_dir: Path,
) -> dict[str, object]:
    ...
```

It accepts no B, source, ref, target, mode, attestation, or receipt override.

Stable candidate failures:

- `interface_candidate:attestation_missing`
- `interface_candidate:attestation_multiple`
- `interface_candidate:schema_mismatch`
- `interface_candidate:owner_mismatch`
- `interface_candidate:owner_surface_mismatch`
- `interface_candidate:repository_mismatch`
- `interface_candidate:aggregate_binding_mismatch`
- `interface_candidate:source_mismatch`
- `interface_candidate:parent_mismatch`
- `interface_candidate:tree_delta_mismatch`
- `interface_candidate:changed_paths_mismatch`
- `interface_candidate:interface_identity_mismatch`
- `interface_candidate:ref_not_full`
- `interface_candidate:ref_missing`
- `interface_candidate:ref_moved`
- `interface_candidate:object_mismatch`
- `interface_candidate:target_tuple_mismatch`
- `interface_candidate:nonce_invalid`
- `interface_candidate:hash_mismatch`
- `interface_candidate:owner_attestation_mismatch`
- `interface_candidate:foreign_b`
- `interface_candidate:stale_attestation`
- `interface_candidate:unattested_b`

### Independent InterfaceCandidateReviewReceipt

Independent review consumes the immutable current attestation. It does not
accept an independently supplied B.

The exact public consumer is:

```python
def review_current_interface_candidate(
    workspace: Path,
    report_dir: Path,
) -> dict[str, object]:
    ...
```

It resolves the current attestation, rereads its candidate ref, validates S,
B, the canonical delta, interface bytes, and intended target tuple, then emits
one immutable receipt.

The receipt body is:

```json
{
  "schema": "agent-canon.interface-candidate-review-receipt.v1",
  "schema_version": 1,
  "receipt_id": "interface-candidate-review:<first-16-attestation-hash>:1",
  "review_round": 1,
  "owner": "ship_reviewer",
  "owner_surface": "documents/REVIEW_PROCESS.md#interface-candidate-review",
  "reviewer_identity": "<independent reviewer identity>",
  "reviewer_separate": true,
  "candidate_attestation_id": "<attestation ID>",
  "candidate_attestation_sha256": "<attestation body SHA256>",
  "reviewed_repository_id": "agent-canon",
  "reviewed_source_commit": "<S>",
  "reviewed_source_tree": "<S tree>",
  "reviewed_candidate_commit": "<B>",
  "reviewed_candidate_tree": "<B tree>",
  "reviewed_candidate_parent": "<S>",
  "reviewed_diff_serialization": "agent-canon.git-tree-delta.v1",
  "reviewed_diff_sha256": "<canonical S-to-B digest>",
  "reviewed_interface_path": "reports/agents/convergence-w2-gates-completion-20260716/ordered_integration_interface.json",
  "reviewed_interface_blob": "<B interface blob>",
  "reviewed_interface_sha256": "<B interface SHA256>",
  "reviewed_target_tuple": {
    "repository_id": "agent-canon",
    "route": "local_ref",
    "mode": "direct_head",
    "target_ref": "refs/heads/<exact target branch>",
    "expected_target_oid": "<G-attested>",
    "expected_target_tree": "<G-attested tree>",
    "remote_name": null,
    "pr_owner_api": null
  },
  "decision": "APPROVE",
  "finding_ids": [],
  "issued_at_utc": "2026-07-16T00:00:00Z",
  "nonce": "<64 lowercase hex>",
  "receipt_body_sha256": "<64 lowercase SHA256>"
}
```

Rules:

1. `decision` is exactly `APPROVE` or `REVISE`.
2. `APPROVE` requires `finding_ids=[]`. `REVISE` requires a non-empty ordered,
   duplicate-free list of typed finding IDs.
3. The reviewer identity is distinct from source writer, candidate writer,
   candidate-attestation owner, component manager, publication owner, and
   integration owner.
4. Every reviewed identity and the target tuple exactly equal the attestation.
5. `receipt_body_sha256` is RFC-8785/SHA256 over the complete receipt without
   `receipt_body_sha256`.
6. The receipt artifact path is exactly
   `reports/agents/convergence-w2-gates-completion-20260716/w2_interface_candidate_review_<first-12-B>_<candidate-version>.md`.
7. The receipt does not contain its own artifact path, complete-file SHA256,
   Git blob, containing commit, or containing tree.
8. After the receipt bytes exist, a later publication-authority event records
   its external path, complete-file SHA256, and Git blob readback.
9. A `REVISE` receipt cannot be promoted. A later review is a new immutable
   receipt and review round.

Stable review failures:

- `interface_candidate_review:missing`
- `interface_candidate_review:multiple`
- `interface_candidate_review:schema_mismatch`
- `interface_candidate_review:owner_mismatch`
- `interface_candidate_review:reviewer_not_separate`
- `interface_candidate_review:attestation_id_mismatch`
- `interface_candidate_review:attestation_hash_mismatch`
- `interface_candidate_review:source_mismatch`
- `interface_candidate_review:candidate_mismatch`
- `interface_candidate_review:diff_hash_mismatch`
- `interface_candidate_review:interface_identity_mismatch`
- `interface_candidate_review:target_tuple_mismatch`
- `interface_candidate_review:decision_invalid`
- `interface_candidate_review:not_approved`
- `interface_candidate_review:hash_mismatch`
- `interface_candidate_review:file_identity_mismatch`
- `interface_candidate_review:foreign_receipt`
- `interface_candidate_review:stale_receipt`

### Post-APPROVE publication authority

`publication_authority` is derived only after an approving receipt exists. It
authorizes publication/integration of the attested candidate; it does not
create or independently establish candidate B.

The exact selected object is:

```json
{
  "schema": "agent-canon.publication-authority.v2",
  "schema_version": 2,
  "publication_id": "w2-publication:<aggregate-sha256>:1",
  "state": "selected",
  "selection_version": 1,
  "selection_owner": "<completion_authority.source_binding.parent>",
  "candidate_authority": {
    "attestation_id": "<current attestation ID>",
    "attestation_body_sha256": "<current attestation hash>",
    "candidate_ref": "<exact immutable candidate ref>",
    "candidate_commit": "<B>",
    "candidate_tree": "<B tree>"
  },
  "approving_review": {
    "receipt_id": "<approving receipt ID>",
    "receipt_body_sha256": "<receipt body hash>",
    "path": "reports/agents/convergence-w2-gates-completion-20260716/w2_interface_candidate_review_<first-12-B>_<candidate-version>.md",
    "sha256": "<external complete-file SHA256>",
    "blob": "<external Git blob>",
    "owner": "ship_reviewer",
    "decision": "APPROVE"
  },
  "source": {
    "commit": "<S>",
    "tree": "<S tree>"
  },
  "target": {
    "repository_id": "agent-canon",
    "route": "local_ref",
    "mode": "direct_head",
    "target_ref": "refs/heads/<exact target branch>",
    "expected_target_oid": "<G-attested>",
    "expected_target_tree": "<G-attested tree>",
    "remote_name": null,
    "pr_owner_api": null
  },
  "selection_sha256": "<64 lowercase SHA256>",
  "owner_attestation": {
    "scheme": "agent-canon-ledger-publication-authority-v2",
    "owner": "<selection owner>",
    "authority_event_id": "<containing aggregate event ID>",
    "authority_revision": 1,
    "candidate_attestation_sha256": "<same candidate hash>",
    "approving_receipt_body_sha256": "<same receipt body hash>",
    "selection_sha256": "<same selection hash>",
    "status": "frozen"
  },
  "result": null
}
```

Publication derivation predicates:

1. The current candidate-attestation pointer resolves exactly one immutable
   attestation and candidate ref B.
2. The selected review receipt is `APPROVE`, externally read back at the
   recorded path/SHA/blob, and binds that exact attestation hash and B.
3. Source and target tuples are byte-for-byte equal across attestation, review
   receipt, and publication authority.
4. `selection_sha256` is RFC-8785/SHA256 over the complete object from
   `candidate_authority` through `target`.
5. The owner attestation binds the candidate hash, review body hash, and
   selection hash.
6. No caller, CLI flag, interface field, branch-name fallback, current HEAD,
   closeout field, or stale publication object can supply B or the target.
7. Later publication revisions repeat the selected tuple byte-for-byte.
8. If target identity changes before CAS, the transaction cannot reuse the
   existing authority. The next candidate version creates a new attestation,
   new immutable candidate ref, new independent receipt, and new publication
   authority. B object bytes may be equal, but the transaction identities and
   target tuple are new.

Stable publication derivation failures:

- `publication_authority:missing`
- `publication_authority:multiple`
- `publication_authority:schema_mismatch`
- `publication_authority:owner_mismatch`
- `publication_authority:owner_attestation_mismatch`
- `publication_authority:selection_hash_mismatch`
- `publication_authority:candidate_attestation_mismatch`
- `publication_authority:candidate_ref_mismatch`
- `publication_authority:review_receipt_mismatch`
- `publication_authority:review_receipt_not_approved`
- `publication_authority:review_file_identity_mismatch`
- `publication_authority:source_mismatch`
- `publication_authority:target_tuple_mismatch`
- `publication_authority:foreign_b`
- `publication_authority:stale_b`
- `publication_authority:foreign_review`
- `publication_authority:stale_review`
- `publication_authority:unattested_b`

### Exact checkout, target, and ancestry predicates

The v4 mode-specific S/B/G/I tree and ancestry predicates remain normative,
with T renamed `G_expected` at the integration linearization point and R
renamed I.

| Phase | Exact allowed checkout/ref identity |
| --- | --- |
| Source implementation start | S, or the exact owner-declared source successor being constructed before source freeze; never an unrelated or moved HEAD. |
| Source freeze | exact approved S commit/tree with clean tracked state. |
| Candidate creation start | exact S commit/tree with clean tracked state. |
| Candidate review | exact attested B commit/tree in the candidate checkout; candidate ref resolves B. |
| Publication preflight | target ref resolves the attested target OID/tree; checkout HEAD, when the target is checked out, equals that OID/tree and is clean. |
| CAS construction | `G_expected` is the final target-ref readback and equals the attested expected target OID/tree. |
| Post-CAS closeout | target ref readback is exact I; when materialized in a checkout, HEAD/tree are exact I and tracked state is clean. |

Common exact predicates:

1. S is the independently approved source-freeze commit/tree.
2. `parent(B) == S`.
3. S→B has exactly the canonical ordered-interface delta.
4. Direct mode requires `G_expected == S` and `I == B`.
5. Merge mode requires S is an ancestor of `G_expected`; I has exactly ordered
   parents `[G_expected, B]`; and `G_expected`→I is the exact interface delta.
6. Cherry-pick mode requires S is an ancestor of `G_expected`; I has exactly
   one parent `G_expected`; and `G_expected`→I is byte-equivalent to S→B under
   the retained canonical delta serialization.
7. No other mode exists.
8. The integration target repository/ref/route/mode/OID/tree exactly equal the
   attestation, approving receipt, and publication authority.
9. A stale, moved, retargeted, symbolic-short, foreign, or differently rooted
   ref fails before integration.

The retained public consumers remain:

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

They accept no B, source, target, mode, ref, attestation, review, publication,
or result override.

### CAS integration linearization

Read/reread verification is preflight. Only the target-ref compare-and-swap is
the integration linearization point.

The future production entrypoint is:

```python
def integrate_selected_publication(
    workspace: Path,
    report_dir: Path,
) -> dict[str, object]:
    ...
```

It accepts no identity override. It derives the current immutable candidate
attestation, approving review receipt, and publication authority.

The exact algorithm is:

1. Acquire the canonical completion-authority writer transaction lock. Record
   the selected aggregate event ID/revision, current intent revision ID/hash,
   candidate attestation ID/hash, review receipt body/file identities,
   publication selection hash, route, mode, target repository, and full target
   ref.
2. Recompute every source, B, canonical tree-delta, candidate-ref,
   reviewer-separation, target-tuple, checkout, and mode predicate.
3. Perform the final target readback. Name the exact ref OID `G_expected` and
   its tree `G_expected_tree`.
4. Require `G_expected` and its tree to equal the frozen target OID/tree in the
   attestation, approving receipt, and publication authority. If not equal,
   stop before object construction with `integration_target_moved`.
5. Reread the selected aggregate/candidate/review/publication objects while
   retaining the writer transaction lock and require byte-identical
   identities.
6. Construct exact result commit I in the object database without moving the
   target ref:
   - direct: I is B and `G_expected == S`;
   - merge: I has first parent `G_expected`, second parent B, and the exact
     validated result tree;
   - cherry-pick: I has one parent `G_expected`, the exact validated result
     tree, and records B as its source candidate.
7. Recompute I's commit/tree/parent/delta predicates from the object database.
8. For a local target, execute only
   `git update-ref <target_ref> <I> <G_expected>` or an owner implementation
   with exactly the same expected-old-OID atomic semantics.
9. For an authorized remote target, execute only an expected-old-OID update
   such as
   `git push --force-with-lease=<target_ref>:<G_expected> <remote> <I>:<target_ref>`
   or an owner API with identical lease semantics.
10. For a PR merge route, call only an owner API that accepts and atomically
    enforces exact expected base OID `G_expected`, exact reviewed head OID B,
    exact target ref, and selected mode. If the API cannot enforce both
    expected OIDs, remain typed blocked.
11. Never run an ordinary merge, cherry-pick, push, ref update, or PR merge
    after validation. No check-then-unconditional-update path is allowed.
12. A nonzero local CAS, failed remote lease, or owner-API expected-OID
    mismatch is `integration_target_moved`. It creates no publication
    completion or pass receipt.
13. After successful CAS, immediately reread the exact local, remote, or
    owner-API target ref. It must resolve I.
14. Generate the immutable `IntegrationCASReceipt` from the frozen transaction
    and actual post-CAS readback.
15. Append the publication result only after the receipt file exists and its
    external path/SHA/blob are read. Release the writer transaction lock only
    after the result append or a typed blocked result.
16. A moved target starts a new candidate/review/publication transaction under
    the next candidate version. The old candidate, review, and publication
    objects remain immutable superseded evidence.

The exact integration receipt body is:

```json
{
  "schema": "agent-canon.integration-cas-receipt.v1",
  "schema_version": 1,
  "receipt_id": "integration-cas:<first-16-selection-hash>:1",
  "owner": "<completion_authority.source_binding.parent>",
  "owner_tool": "tools/agent_tools/publication_integrator.py",
  "aggregate_identity": "<aggregate identity>",
  "aggregate_revision": 1,
  "current_intent_revision_id": "<current intent revision ID>",
  "candidate_attestation_id": "<attestation ID>",
  "candidate_attestation_sha256": "<attestation body hash>",
  "candidate_commit": "<B>",
  "review_receipt_id": "<approving review receipt ID>",
  "review_receipt_body_sha256": "<approving receipt body hash>",
  "publication_selection_sha256": "<selection hash>",
  "route": "local_ref",
  "mode": "direct_head",
  "target_ref": "refs/heads/<exact target branch>",
  "expected_old_oid": "<G_expected>",
  "expected_old_tree": "<G_expected tree>",
  "result_commit": "<I>",
  "result_tree": "<I tree>",
  "result_parents": ["<ordered parent OIDs>"],
  "cas_operation": "git-update-ref-expected-old-v1",
  "cas_status": "success",
  "post_cas_ref_oid": "<I>",
  "post_cas_ref_tree": "<I tree>",
  "completed_at_utc": "2026-07-16T00:00:00Z",
  "receipt_body_sha256": "<64 lowercase SHA256>"
}
```

Route-specific `cas_operation` values are exactly:

- `git-update-ref-expected-old-v1`;
- `git-push-force-with-lease-exact-v1`; or
- `owner-pr-merge-expected-base-head-v1`.

The receipt path is exactly
`reports/agents/convergence-w2-gates-completion-20260716/w2_integration_cas_receipt_<first-12-I>_<candidate-version>.json`.
The receipt is generated by the owner tool, never hand-written. It does not
contain its own path, complete-file SHA256, Git blob, containing commit, or
containing tree. `receipt_body_sha256` excludes itself and uses RFC-8785 JSON
UTF-8 with no BOM or trailing newline.

The later publication result records:

```json
{
  "selection_sha256": "<unchanged selection hash>",
  "integration_receipt": {
    "receipt_id": "<integration receipt ID>",
    "receipt_body_sha256": "<receipt body hash>",
    "path": "reports/agents/convergence-w2-gates-completion-20260716/w2_integration_cas_receipt_<first-12-I>_<candidate-version>.json",
    "sha256": "<external complete-file SHA256>",
    "blob": "<external Git blob>"
  },
  "expected_old_oid": "<G_expected>",
  "result_commit": "<I>",
  "result_tree": "<I tree>",
  "post_cas_ref_oid": "<I>",
  "integrated_at_revision": 1,
  "result_sha256": "<64 lowercase SHA256>"
}
```

`result_sha256` excludes itself. The selected publication tuple remains
byte-for-byte unchanged. Completion requires
`result_commit == post_cas_ref_oid == integration receipt result_commit ==
integration receipt post_cas_ref_oid`.

Stable CAS failures:

- `integration_target_moved`
- `integration_result_parent_mismatch`
- `integration_result_tree_mismatch`
- `integration_result_delta_mismatch`
- `integration_local_cas_failed`
- `integration_remote_lease_failed`
- `integration_pr_cas_unsupported`
- `integration_pr_expected_base_mismatch`
- `integration_pr_expected_head_mismatch`
- `integration_post_cas_ref_mismatch`
- `integration_receipt_generation_failed`
- `integration_receipt_body_hash_mismatch`
- `integration_receipt_file_identity_mismatch`
- `integration_receipt_selection_mismatch`
- `integration_result_append_conflict`
- `integration_ordinary_update_forbidden`

No CAS failure, receipt failure, or result-append conflict produces a success
projection. If CAS succeeded but later evidence binding is blocked, the actual
ref readback remains the external fact and closeout remains typed blocked until
the owner route binds that fact; no hand-written success artifact is allowed.

### Complete non-self-referential publication DAG

The publication graph is:

```text
approved design D
  -> source-freeze commit/tree S
  -> interface-only direct child B
  -> owner-attested candidate A
  -> independent review receipt CR
  -> post-APPROVE publication authority PA
  -> exact result object I
  -> expected-old-OID CAS target readback I
  -> generated integration receipt IR
  -> later result-binding aggregate event RB
  -> integration/closeout consumers
```

| Node | Owner | Required identity fields | External binding |
| --- | --- | --- | --- |
| D | design author/reviewer | design path and predecessor/review tuple | containing commit/tree/blob/SHA are external only |
| S | source implementation owner | commit, tree, canonical source diff | later A and CR bind S |
| B | interface candidate owner | commit, tree, parent S, canonical delta, interface blob/SHA | A binds B and immutable candidate ref |
| A | canonical parent/integration owner | attestation ID/body hash, S/B/ref/target tuple, owner attestation | CR and PA bind A |
| CR | independent `ship_reviewer` | receipt body hash, A hash, S/B/delta/target, decision | PA records CR path/file SHA/blob |
| PA | canonical parent/integration owner | A hash, CR body/file identity, target tuple, selection hash | integration owner derives all inputs from PA |
| I | integration owner tool | commit, tree, ordered parents, mode delta | target CAS readback binds I |
| IR | integration owner tool | receipt body hash, expected old OID, I, post-CAS I | RB records IR path/file SHA/blob |
| RB | canonical ledger owner | PA selection hash, IR body/file identity, I/readback equality | closeout recomputes all predecessors |

No node hashes its own complete bytes. No artifact requires its own containing
commit/tree/blob. No durable owner document depends on D, CR, IR, or another
run-local report.

### Preserved convention-consistency closure

The complete retained direct closure is:

| Owner/path | Exact edge/responsibility |
| --- | --- |
| `documents/REVIEW_PROCESS.md` | `downstream implementation ../tools/check_convention_consistency.py parses review-policy rules for convention contradiction checks` |
| `tools/check_convention_consistency.py` | `upstream design ../documents/REVIEW_PROCESS.md review-policy rule source` |
| `tools/README.md` | `downstream implementation ./check_convention_consistency.py convention consistency checker` |
| `tools/check_convention_consistency.py` | retained `upstream design README.md shared automation index` |
| `tools/check_convention_consistency.py` | `downstream implementation ./run_comprehensive_review.sh invokes checker` |
| `tools/run_comprehensive_review.sh` | `upstream implementation ./check_convention_consistency.py convention consistency check` |
| `tools/check_convention_consistency.py` | `downstream implementation ../tests/agent_tools/test_check_convention_compliance.py verifies convention consistency behavior and wiring` |
| `tests/agent_tools/test_check_convention_compliance.py` | `upstream implementation ../../tools/check_convention_consistency.py convention consistency behavior under test` |

`tools/agent_tools/check_convention_compliance.py` and
`tools/agent_tools/tool_drift.py` select and validate this closure. The two
shell call sites remain one implementation dependency. No duplicate owner,
conflicting edge, or run-local upstream is introduced.

## Rejected Alternatives

- A publication authority that first invents B after review is rejected as
  circular.
- A caller-supplied B, current HEAD, branch tip, filename suffix, interface
  field, or closeout field as candidate authority is rejected.
- Reusing a review for a different attestation hash, target tuple, candidate
  version, or B is rejected.
- Treating an approving review receipt as candidate-existence authority is
  rejected; it is independent evidence about an already attested candidate.
- Treating preflight rereads as sufficient integration safety is rejected.
- Ordinary merge, cherry-pick, push, ref update, or PR merge after validation
  is rejected because it is not expected-old-OID atomic.
- A PR API without exact expected base and reviewed head predicates is rejected
  and remains typed blocked.
- Mutating a historical intent row to mark it superseded is rejected.
- Keeping both a copied `current_intent` object and a history row is rejected.
- A second logical key for changed intent is rejected.
- A formatter pending string, missing event, null artifact placeholder, or
  hand-written pending/pass receipt is rejected.
- A terminal-to-pending transition or mutation of the old pending event is
  rejected.
- A compatibility selector or test-only production entrypoint is rejected.

## Abstract Design Frame

### Replaceable responsibility unit

D1-D5 and F1-F6 remain one replaceable
`completion_authority` responsibility unit:

1. maintain one canonical ledger L, one logical aggregate key, immutable intent
   revisions, and one current intent pointer;
2. append owner-typed canonical source/evidence events;
3. derive schedule, open work, repair, crossing edges, topology, formatter,
   descendant, and completion facts from L plus exact Git/artifact readback;
4. attest candidate B before review through the canonical owner;
5. obtain an independent review receipt bound to the attestation hash and B;
6. derive post-APPROVE publication authority from the attestation, receipt, and
   frozen target tuple;
7. construct I from exact `G_expected` and linearize publication through an
   expected-old-OID CAS;
8. bind completion to the actual post-CAS ref readback and generated receipt;
9. preserve per-member source correspondence and exact group equality; and
10. preserve durable forward/reverse dependency closure.

An implementation slice is replaceable only if all public signatures, schemas,
hash ranges, owner relations, equality/ancestry predicates, typed errors,
negative oracles, and dependency edges remain unchanged.

### Authority and projection

L is the sole authority. Projection P is pure:

`P = f(L, canonical Git object/ref readback, canonical artifact readback)`.

Stored status, success, topology, formatter, descendant, publication, or
completion views are projection-only and fingerprint-bound. Every consumer
recomputes gates, topology, evidence selection, and completion. No stored
success boolean, report prose, hand-written receipt, or group-shared inference
overrides canonical events and readback.

### Invariants

- One run has one aggregate identity, one logical key, one ordered intent list,
  and one current intent pointer.
- Historical intent and evidence rows are immutable.
- Every member resolves its own owner/responsibility/outcome/evidence source
  event before group equality is checked.
- Formatter pending is a canonical event, not absence of evidence.
- Candidate B exists by pre-review owner attestation.
- Review independently evaluates that immutable attestation and B.
- Publication authority exists only after APPROVE.
- The target ref is changed only by exact expected-old-OID CAS.
- Completion binds the actual post-CAS readback I.
- Freeze, topology, order, identity, source, target, and group predicates are
  exact.
- No node is self-referential.

### Non-goals

- No source, Python, test, owner-document, formatter, CI, or dynamic-graph
  change or execution in v5.
- No new ledger, persistence service, cryptographic key infrastructure,
  compatibility selector, test-only API, alternate interface, or inferred
  success path.
- No change to the canonical tree-delta bytes, branch reason, D2/D3/F1/F2,
  topology truth table, or convention closure.

## Implementation Source Packet

### Bound predecessor and review identities

- Source predecessor commit:
  `80e63c4134058204e243c6140522d9e3671f9de6`
- Source predecessor tree:
  `5174b0dc1426e6afe8db78ba5f43a2320e79feef`
- v4 design commit:
  `9825c7a67fc736c2ac40ef3e8ab0585e36bcf3cd`
- v4 design tree:
  `3d2321f1a247665397c6a3c2e0d15cb043c0a22d`
- v4 direct parent:
  `a2cebf5239d80b044453bed2e58f9fa7e988991d`
- v4 design path:
  `reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v4.md`
- v4 design SHA256:
  `65346e97e3f7062db4b8030555d485ac75038c36e223365a432cbd647f1f353b`
- v4 design blob:
  `e5b9006dc85e011e40a9a1294523c1004f628710`
- v4 independent REVISE path:
  `/mnt/l/workspace/agent-canon-convergence-w2-final-writer-owned/reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_9825c7a6.md`
- v4 recheck SHA256:
  `ffafb236cf9399bafd2acf15c211f7160bebd5984605930427ded688dcdec1f5`
- v4 recheck blob:
  `33b548aeb8e02ea6a47df9f62ee7ace36d413448`

The independent decision is `REVISE` with exactly four findings:

1. candidate B lacks a non-circular pre-review owner authority;
2. reread verification is not the actual integration linearization;
3. intent current/history shapes conflict with immutability; and
4. formatter pending lacks a canonical event.

The same decision confirms convention closure and D2/D3/F1/F2 have no
regression. This v5 design changes only those four findings.

### Mandatory implementation read order

1. This v5 artifact.
2. The bound v4 review decision and v4 design.
3. The retained v3 design and its bound review.
4. `COMMUNICATION_PROTOCOL.md`, `CODEX_WORKFLOW.md`, and
   `REVIEW_PROCESS.md`.
5. `work_log.py`, `workflow_monitor.py`, `report_artifact_checks.py`,
   `waterfall_gate_check.py`, and `task_close.py`.
6. The exact convention-consistency owner/caller/test/document paths.
7. Every retained v3/v4 Side-Effect Map path.

### Implementation boundary

Implementation remains blocked until independent approval of this exact v5
artifact. Source-freeze S must contain the approved implementation, owner
documents, headers, tests, and public consumers, excluding only the later
ordered-interface candidate B. No implementation starts from this design
commit merely because it exists.

## Design Side-Effect Map

| Path | Exact future change | Clause | Gate |
| --- | --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | Replace copied current intent with immutable intent rows/pointer; add pending tagged event and current-event pointer rules. | V5-P1-A/B | Schema-owner review |
| `agents/canonical/CODEX_WORKFLOW.md` | Add candidate owner/ref/attestation transaction, post-review publication derivation, target freeze, CAS route, and retry transaction. | V5-P0-A/B | Workflow-owner review |
| `documents/REVIEW_PROCESS.md` | Define independent candidate-receipt fields, reviewer separation, APPROVE/REVISE rules, and generated integration-receipt review. | V5-P0-A/B | Review-owner review |
| `documents/dependency-manifest-design.md` | Apply existing exact closure rules; no semantic generalization. | PRESERVE | Dependency review |
| `tools/README.md` | Route candidate/publication/CAS owner tool and retain convention-checker navigation edge. | V5-P0-B, PRESERVE | Docs review |
| `tools/agent_tools/work_log.py` | Validate immutable intent rows/pointer, pending transitions, candidate/current pointers, structural owner attestations, publication/result append order. | V5-P0-A, V5-P1-A/B | Ledger tests/review |
| `tools/agent_tools/workflow_monitor.py` | Preserve tagged pending/terminal canonical evidence payloads and pointers unchanged. | V5-P1-B | Monitor tests |
| `tools/agent_tools/report_artifact_checks.py` | Resolve attestation/review/publication without overrides; verify immutable refs, pointer/hash equality, target tuple, CAS receipt, and post-CAS result. | all | Public verifier tests |
| `tools/agent_tools/publication_integrator.py` | New focused production owner unit: derive authority, construct I, perform exact CAS, reread target, generate receipt. | V5-P0-A/B | Integration-owner review |
| `tools/agent_tools/task_close.py` | Invoke no-override final consumer; require CAS receipt/result/readback equality; expose typed failures. | V5-P0-B | Public closeout tests |
| `tools/agent_tools/waterfall_gate_check.py` | Validate phase HEAD/ref/source/candidate/target facts without performing integration. | V5-P0-A/B | Public gate tests |
| `agents/templates/change_review.md` | Present attestation hash/B/S/delta/target fields; no caller B field. | V5-P0-A | Template review |
| `agents/templates/final_review.md` | Verify APPROVE receipt, publication derivation, expected-old OID, CAS operation, receipt, and readback. | V5-P0-A/B | Final-review gate |
| `agents/templates/closeout_gate.md` | Record derived publication/result/receipt identities only. | V5-P0-B | Closeout review |
| `.codex/agents/ship_reviewer.toml` | Require attestation-bound independent candidate review and CAS-result evidence. | V5-P0-A/B | Runtime alignment |
| `tools/check_convention_consistency.py` | Retain direct REVIEW_PROCESS consumer edge and behavior. | PRESERVE | Checker review |
| `tools/run_comprehensive_review.sh` | Retain one reverse call dependency. | PRESERVE | Shell/checker review |
| `tools/agent_tools/check_convention_compliance.py` | Retain exact owner/reverse/caller/test/doc edge validation. | PRESERVE | Convention tests |
| `tools/agent_tools/tool_drift.py` | Retain selected direct consumer/caller in drift checks. | PRESERVE | Drift tests |
| `tests/agent_tools/test_work_log.py` | Intent pointer/immutability, candidate/publication derivation, pending transitions, and typed negatives. | V5-P0-A, V5-P1-A/B | Oracle review |
| `tests/agent_tools/test_workflow_monitor.py` | Pending and terminal payload/pointer round trip and malformed transition negatives. | V5-P1-B | Oracle review |
| `tests/agent_tools/test_report_artifact_checks.py` | Public attestation/review/publication/result resolvers and foreign/stale/hash/ref negatives. | V5-P0-A/B | Oracle review |
| `tests/agent_tools/test_publication_integrator.py` | Local CAS, remote lease, PR expected-OID, target-move race, receipt/readback, and no ordinary-update oracles. | V5-P0-B | Oracle review |
| `tests/agent_tools/test_task_start_and_close.py` | Final public completion failures for stale B/review/target, missing CAS receipt, and readback mismatch. | V5-P0-A/B | Oracle review |
| `tests/agent_tools/test_waterfall_gate_check.py` | Source/candidate/target checkout identity and retarget negatives. | V5-P0-A/B | Oracle review |
| `tests/agent_tools/test_check_convention_compliance.py` | Retain exact convention direct and reverse-edge oracles. | PRESERVE | Oracle review |
| ordered interface path | Retain exact v3 schema/tree shape; never select its containing B or hash its own containing object. | PRESERVE | Independent candidate review |

Every non-conflicting v3/v4 Side-Effect Map row remains in scope.

## Design-to-Implementation Trace

| Slice | Responsibility derivation | Future paths | Clauses | Gate |
| --- | --- | --- | --- | --- |
| S1 Intent authority | One key, immutable rows, one pointer | protocol, workflow, work log, report checks | V5-P1-A | Ledger/public negative tests |
| S2 Pending evidence | Pending is a canonical immutable event with one legal terminal transition | protocol, monitor, work log, report checks | V5-P1-B | Round-trip/transition tests |
| S3 Candidate authority | Owner attests S/B/ref/delta/target before review | workflow, work log, report checks | V5-P0-A | Owner and public resolver review |
| S4 Independent review | Receipt consumes immutable attestation and cannot invent B | review owner/templates/reviewer | V5-P0-A | Separate APPROVE review |
| S5 Publication derivation | APPROVE receipt plus candidate and target produce authority | workflow, work log, report checks | V5-P0-A | Derivation/hash tests |
| S6 CAS result | Build I from final G and update only with expected-old OID | publication integrator | V5-P0-B | CAS/race tests |
| S7 Result binding | Generated receipt and post-CAS readback bind completion | integrator, report checks, task close | V5-P0-B | Closeout/public tests |
| S8 Convention closure | One durable policy owner and exact direct/reverse consumers | retained R3 paths | PRESERVE | Header/checker review |
| S9 Retained authority | D2/D3/F1/F2, topology, tree delta, member equality | all retained v3/v4 paths | PRESERVE | Regression review |
| S10 Source freeze | Freeze S1-S9 before B | S commit/tree | all | External readback |

## Exact Acceptance Predicates

### Finding 1: two-stage B authority

Pass if and only if:

1. one current owner-attested candidate exists before review;
2. its owner identity/surface, repo, S, B, parent, tree delta, interface,
   immutable ref, target tuple, timestamp, nonce, body hash, and structural
   owner attestation validate exactly;
3. no public caller supplies B or another selection identity;
4. an independent receipt resolves that attestation and binds the same hash,
   S, B, delta, interface, and target;
5. reviewer separation validates;
6. only `APPROVE` with no findings can derive publication authority;
7. publication authority binds external receipt path/SHA/blob and exact
   candidate/target identities;
8. publication authority authorizes integration but is not candidate-existence
   authority; and
9. foreign, stale, moved, unattested, mismatched, or unapproved B/review facts
   fail typed.

### Finding 2: actual CAS integration

Pass if and only if:

1. final target readback yields `G_expected` equal to the frozen target tuple;
2. I is constructed without moving the ref and has exact mode-specific
   parent/tree/delta structure based on `G_expected`;
3. local publication uses expected-old `git update-ref` semantics;
4. remote publication uses exact expected-old lease semantics;
5. PR publication uses an owner API enforcing expected base and reviewed head,
   or remains typed blocked;
6. no ordinary update occurs after validation;
7. target movement causes `integration_target_moved`, no completion, and a new
   candidate/review transaction;
8. successful CAS is followed by exact target-ref readback I;
9. a generated immutable receipt binds expected old OID, B, authority, I, and
   post-CAS I; and
10. closeout recomputes receipt/file/result/ref equality.

### Finding 3: immutable intent schema

Pass if and only if:

1. the aggregate has one fixed logical key;
2. `intent_revisions` contains only exact immutable
   `IntentRevisionRecord.v1` rows;
3. the aggregate contains only one `current_intent_revision_id` pointer for
   current-intent selection;
4. the pointer resolves the last row;
5. same-intent revisions do not alter list or pointer;
6. changed intent appends one consecutive row and advances the pointer;
7. supersession is derived from pointer/order without history mutation;
8. consumers dereference the row and compare exact version/fingerprint;
9. old-intent evidence cannot satisfy current gates; and
10. duplicate IDs, missing/forked pointers, non-monotone versions, row
    mutation, and hash mismatch fail typed.

### Finding 4: canonical formatter pending

Pass if and only if:

1. pending is an exact canonical evidence event;
2. pending has empty evidence refs and omits artifact/completion fields;
3. the formatter pending record references its exact event ID/hash;
4. pass/fail is a new immutable event for the same aggregate revision/key;
5. pass/fail supersedes the exact pending head and supplies required terminal
   evidence/artifact/completion fields;
6. the old pending event remains history and the current pointer advances;
7. no terminal-to-pending or other illegal transition is accepted;
8. descendant and formatter consumers use the same common schema and exact
   pointer/hash equality; and
9. missing, foreign, stale, out-of-order, schema-mismatched, field-mismatched,
   or transition-invalid events fail typed.

### Preserved F1-F6

- F1: L is sole authority; P is recomputed from L and canonical readback.
- F2: every member's owner, responsibility, outcome, and evidence come from
  that member's own canonical source event.
- F3: exact `freeze=true`, topology state, order, identity, repair-return, and
  escalation predicates remain the retained truth-table oracle.
- F4: D→S→B→attestation→review→publication→CAS→receipt→binding is acyclic and
  no artifact hashes its own complete bytes or containing Git identity.
- F5: all hand-written mutation, member mismatch/missing, freeze false,
  topology missing/order mutation, candidate/review, intent, pending, and CAS
  failures have typed public negative tests.
- F6: OOP/SOLID/formatter/static/test execution remains pending until
  consolidated implementation validation; no hand-written pass artifact is
  created.

### Preserved D2 and D3

- D2: the sole positive branch-creation reason is exactly
  `convergence_w2_gate_completion_authority`; stale interface text is not
  authority.
- D3: after per-member event resolution, every group member exactly equals the
  baseline on owner, state, API/dependency owner, responsibility unit, outcome,
  and ordered approved evidence. Missing/member mismatch remains typed.

### Public typed negative-test plan

| Negative | Public boundary | Typed result |
| --- | --- | --- |
| Caller supplies B | candidate/publication resolver | API rejects the parameter; no compatibility route |
| Candidate attestation missing | candidate resolver | `interface_candidate:attestation_missing` |
| Candidate ref moved after attestation | candidate/publication resolver | `interface_candidate:ref_moved` |
| B has foreign parent or extra path | candidate resolver | `parent_mismatch` or retained canonical delta error |
| Unattested valid B substituted | task close | `interface_candidate:unattested_b` |
| Stale candidate version selected | publication resolver | `interface_candidate:stale_attestation` |
| Review binds another attestation hash | publication resolver | `interface_candidate_review:attestation_hash_mismatch` |
| Review binds another B or target | publication resolver | exact candidate/target mismatch |
| Reviewer is not separate | review/publication resolver | `interface_candidate_review:reviewer_not_separate` |
| REVISE receipt promoted | publication resolver | `interface_candidate_review:not_approved` |
| Foreign/stale receipt file | publication resolver | exact foreign/stale/file-identity error |
| Target moves after preflight before local CAS | integration owner public entrypoint | `integration_target_moved` |
| Local ref update omits expected old OID | integration owner boundary | `integration_ordinary_update_forbidden` |
| Remote push lacks exact lease | integration owner boundary | `integration_ordinary_update_forbidden` |
| Remote expected-old lease fails | integration owner boundary | `integration_target_moved` |
| PR API lacks expected base/head | integration owner boundary | `integration_pr_cas_unsupported` |
| Constructed I has wrong first parent/base | integration verifier | `integration_result_parent_mismatch` |
| Constructed I has wrong tree/delta | integration verifier | exact tree/delta mismatch |
| Post-CAS ref is not I | integration/closeout | `integration_post_cas_ref_mismatch` |
| Receipt binds another selection or I | closeout | `integration_receipt_selection_mismatch` |
| Duplicate intent revision ID | work-log resolver | `intent_revision_duplicate_id` |
| Current pointer missing/not found | work-log resolver | exact current-pointer error |
| Pointer is not last row | work-log resolver | `intent_current_pointer_not_last` |
| Two selected pointer heads | work-log resolver | `intent_multiple_current_pointers` |
| Intent version regresses/skips | work-log resolver | exact non-monotone/gap error |
| Prior intent row changes bytes | work-log resolver | `intent_revision_mutated` |
| Intent row hash differs | work-log resolver | `intent_revision_hash_mismatch` |
| Pending formatter event absent | formatter consumer | `pending_event_missing` |
| Pending event has artifact or completion | work-log/public consumer | exact pending-forbidden error |
| Pending evidence refs are non-empty | work-log/public consumer | `pending_evidence_refs_not_empty` |
| Pass/fail omits terminal evidence | work-log/public consumer | exact terminal-field error |
| Pass/fail transitions back to pending | work-log/public consumer | `terminal_to_pending_forbidden` |
| Terminal event skips pending head | work-log/public consumer | `invalid_transition` or `supersedes_mismatch` |
| Current formatter pointer names old pending | formatter consumer | `current_pointer_not_head` |
| Event pointer hash differs | formatter/descendant consumer | `current_pointer_hash_mismatch` |
| Foreign/stale/schema-mismatched event | formatter/descendant consumer | retained exact canonical-evidence error |
| Hand-written success artifact | report/task-close consumer | non-canonical evidence typed failure |
| Member event missing/mismatched | group consumer | retained D3 typed member error |
| `freeze=false` | topology consumer | retained exact freeze failure |
| Topology state missing/order changed | topology consumer | retained exact topology/order failure |
| Convention direct/reverse edge missing | convention checker | retained exact dependency finding |

Positive public lifecycle cases:

- same logical key appends one changed-intent row and advances one pointer;
- formatter pending advances to a new immutable pass or fail event;
- candidate B is attested before independent review;
- an APPROVE receipt derives publication authority without reselecting B;
- local expected-old CAS succeeds only from exact `G_expected`;
- remote lease and PR owner API enforce equivalent expected-OID semantics;
- post-CAS receipt and closeout resolve exact I;
- all retained D2/D3/F1/F2 and topology/tree-delta cases continue to pass.

### Validation honesty

- `oop_readability=pending`
- `solid_evidence=pending`
- `formatter=pending`
- `selected_non_python_static=pending`
- `targeted_tests=pending`
- `python_execution=deferred_by_user`
- `ci=deferred_by_user`
- `dynamic_graph=deferred_by_user`
- `dependency_graph_execution=deferred_by_user`
- `implementation_authorization=blocked_until_independent_v5_design_approval`

No source, Python, test, formatter, CI, or dynamic command is promoted to pass
by this design. No hand-written pass artifact may satisfy a gate.
