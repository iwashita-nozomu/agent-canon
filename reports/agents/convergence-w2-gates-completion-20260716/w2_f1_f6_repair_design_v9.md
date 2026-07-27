# W2 F1-F6 Repair Design v9

## Reader Map

This append-only v9 design simplifies exactly two v8 contracts inside the same
`completion_authority` responsibility unit:

1. reviewer terminal resume/replacement becomes the one-way immutable DAG
   `intent -> frame -> event -> external binding -> current pointer`; and
2. external provider authority is removed from generic Git/file
   `source_binding` and owned by one exact external binding event.

Read in this order:

1. `Structure Contract And Source-Truth Projection` fixes the replacement
   boundary.
2. `Request Clauses`, `Owner Surfaces`, and `Normative Incorporation Of v8`
   identify what changes and what remains unchanged.
3. `Selected Architecture` defines the one-way DAG, schemas, IDs, null rules,
   write order, and readback.
4. `Implementation Source Packet`, `Design Side-Effect Map`, and
   `Dependency-Header Closure` bind later implementation scope.
5. `Design-to-Implementation Trace`, `Exact Acceptance Predicates`, and
   `Public Typed Negative-Test Plan` are the independent-review oracle.

This artifact is a compact delta over v8. The implementation packet is v8 plus
v9. When text conflicts, v9 replaces v8 only for reviewer-resume object order,
frame/event identity, external provider binding, and generic
`source_binding`. Every other v8 clause remains normative.

This artifact intentionally contains no identity for its own complete bytes,
Git blob, containing commit, tree, or byte size. Those are external readback
evidence.

## Structure Contract And Source-Truth Projection

```text
structure_kind=document
audience=independent detailed-design reviewer and later implementation owner
decision_context=whether the v8 reviewer-resume and external-binding schemas are acyclic and implementation-ready
first_artifact=mermaid one-way immutable reviewer-resume DAG
first_artifact_question=does every object depend only on already durable objects and does provider authority bind only after local event creation
visual_plan=mermaid DAG plus exact schema/null-rule tables
document_unit=owner W2 design author; reader independent reviewer/implementer; source map exact v8 commit/artifacts and bounded reviewer-resume/artifact-binding owner paths; validation static Markdown/Git/hash; update cadence append-only review successor; canonical parent v8; downstream independent v9 review
document_split_decision=split:append-only v9 has a new review identity and fixed-byte request while preserving the v8 responsibility owner
metric_or_delta_contract=zero future-object references; five ordered durable stages; two generic source-binding variants; one external binding event; zero v8 pass regressions
invalid_interpretations=v9 is not source authorization, not permission to mutate v8 history, not a compatibility selector, not a second ledger, and not approval inferred from an external receipt
validation_gate=independent fixed-byte v9 detailed-design review
```

Static source-truth anchors and typed relations:

| Anchor | Source truth | Typed relation | v9 result |
| --- | --- | --- | --- |
| `V9-R1` | v8 frame names a future event and v8 authority/frame fields mutually depend | `requires` acyclic construction; `limits` forward references | intent is durable before frame; frame before event; event before binding; binding before current pointer |
| `V9-R2` | v8 generic artifact identity includes `external_immutable_receipt` | `requires` local-byte/provider separation | generic source binding is only committed Git bytes or immutable filesystem bytes; provider authority is one later binding event |
| `PRESERVE` | v8 exact acceptance predicates | `constrains` both repairs | corrected v6 identity, tool-imported hashes, README edges, checkout authority, publication, recovery, automatic review, formatter union, D2/D3/F1/F2, and non-self-reference remain |

No dynamic graph was generated. The Mermaid and tables are a static projection
because Python and dynamic-graph execution remain deferred.

## Request Clauses

| Clause | Required closure |
| --- | --- |
| V9-R1 | Replace the cyclic terminal-review schema with one immutable DAG: intent, frame, event, external binding, current pointer. No object ID/hash/reference may depend on a future object. Define exact write, fsync, readback, crash-resume, and pointer order. |
| V9-R2 | Remove `external_immutable_receipt` from generic artifact `source_binding`. Define one exact external binding event with provider/object/receipt identity, null rules, deterministic ID seed, canonical hash, equality, and public negative oracles. |
| PRESERVE | Preserve every v8 acceptance predicate and non-regression requirement. |
| BOUNDARY | Change only v9 design/request artifacts. Source, tests, owner docs, hooks, Python, CI, and implementation remain blocked. |

## Owner Surfaces

| Responsibility | Canonical owner | Replaceable unit | Consumers |
| --- | --- | --- | --- |
| reviewer-resume packet and event schemas | `agents/COMMUNICATION_PROTOCOL.md` | future `tools/agent_tools/review_dispatch.py` | team routing, workflow monitor, report checks, publication lock |
| reviewer lifecycle and terminal authority | `agents/canonical/CODEX_SUBAGENTS.md`, `agents/task_catalog.yaml`, `agents/agents_config.json` | `agent_team.py` plus runtime adapter | parent monitor/integrator and reviewer role instance |
| canonical review/publication state | `agents/canonical/CODEX_WORKFLOW.md`, ledger L | atomic ledger writer | review dispatcher, publication integrator, task close |
| local Git/file byte identity | `agents/COMMUNICATION_PROTOCOL.md` | future `tools/agent_tools/artifact_identity.py` | review/publish packet generators |
| external provider/object/receipt binding | `agents/COMMUNICATION_PROTOCOL.md` | future `tools/agent_tools/external_artifact_binding.py` | review dispatcher, GitHub publish, publication integrator |
| external projection/readback | `github_publish.py`, runtime provider adapter | provider-specific read-only query | external binding materializer and closeout |

Durable canon never depends upstream on this run-local v9 artifact.

## Normative Incorporation Of v8

The exact v8 predecessor is:

```text
commit=0c5bfb817f1db7c0dee2026f9938ebe7139bb4eb
tree=0992f17f6f1b8981fd3e47b164020023924a7b3e
parent=3fab576c1bf1a4621ae69778859b441fbaf7bda9
design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v8.md
design_size_bytes=205113
design_sha256=7c310a2befb32290781a42ab9b2043b405a18da5cecf6598784c10096519659a
design_git_blob=f1d612ae990ad9b810cef475992a6e6873c68118
request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v8.md
request_size_bytes=9714
request_sha256=0961bc7fc48b5fa4e4d14ff9f9c7f07c6421aced9db811b6665adafd8339c608
request_git_blob=b4eb8f7b4388e2df7208f76fcb8ca8a7a7459621
```

v9 supersedes only these v8 clauses:

1. `AutomaticReviewFrame v2` `resume_transition.expected_event_id`;
2. the pre-dispatch replacement-authority receipt that includes frame identity
   while the frame includes that receipt identity;
3. terminal event ID derivation that is precomputed in the frame;
4. current review-state advancement before a later external provider binding is
   durable; and
5. `ArtifactIdentityRecord` generic source kind
   `external_immutable_receipt`.

The following v8 findings remain passed and unchanged:

- V8-I1 corrected v6 request blob
  `6ff0191daf02f86b6642bfb2762db6ccc702fdbe`;
- V8-I2 tool-materialized size/SHA/blob/path/source identity and structured
  packet import, except for the removed generic external source variant;
- V8-D1 four exact root README checker/test reciprocal pairs;
- V8-L1 reviewer independence, same context, terminal status algebra,
  compaction-safe locator, typed blockers, and no prompt/fresh/self-review
  bypass, with construction order replaced by V9-R1;
- V8-P1 exact approved candidate-OID publication, explicit refspec or clean
  true-clone route, and no auto-include/revert of dirty checkout changes;
- V6-R1, V6-R2, V7-A1, publication CAS, immutable B/intent, canonical ledger,
  per-member correspondence, group equality, topology/freeze, five formatter
  statuses, D2/D3/F1/F2, and non-self-reference.

No compatibility reader accepts the superseded frame/event/source-binding
schemas.

## Selected Architecture

### One-way immutable reviewer-resume DAG

```mermaid
flowchart LR
  L0["Current ledger state + terminal observation"] --> I["ResumeIntent v1"]
  I --> F["AutomaticReviewFrame v3"]
  F --> D["Provider dispatch"]
  D --> E["ResumeEvent v2"]
  E --> X["ExternalArtifactBindingEvent v1"]
  X --> P["Atomic current-pointer update"]
  P --> R["Post-update readback"]
```

The arrows are the only legal identity/reference direction. Each node may hash
or identify itself from already durable predecessors and its own non-hash
fields. It may not contain an ID, hash, path binding, or pointer for a node to
its right.

Exact prohibitions:

- intent contains no frame, event, external-binding, or current-pointer ID/hash;
- frame contains intent ID/hash but no event, binding, or pointer ID/hash;
- event contains intent/frame IDs/hashes but no binding or pointer ID/hash;
- external binding contains intent/frame/event IDs/hashes but no current-pointer
  ID/hash;
- current pointers reference only the fully read-back external binding and its
  predecessor chain; and
- no deterministic ID seed includes a future artifact's bytes, path, hash,
  provider ID, or result.

### Simplified generic artifact source binding

v9 replaces `agent-canon.artifact-identity.v1` with
`agent-canon.artifact-identity.v2`. The complete record remains as defined by
v8 except:

```json
{
  "source_binding": {
    "kind": "git_commit_path",
    "commit": "<40 lowercase Git OID or null>",
    "tree": "<40 lowercase Git OID or null>",
    "path_mode": "100644",
    "tree_blob": "<40 lowercase Git OID or null>"
  }
}
```

Allowed `source_binding.kind` is exactly:

- `git_commit_path`; or
- `filesystem_immutable`.

Null rules:

| Kind | `commit` | `tree` | `path_mode` | `tree_blob` | Byte source |
| --- | --- | --- | --- | --- | --- |
| `git_commit_path` | non-null | non-null | non-null six-digit Git mode | non-null | exact committed tree-entry bytes |
| `filesystem_immutable` | null | null | non-null observed regular-file mode | null | one stable no-follow filesystem read |

The string `external_immutable_receipt` is invalid in schema v2. External
receipt bytes are first materialized as `filesystem_immutable`; provider
authority is attached only by `ExternalArtifactBindingEvent v1`. A later Git
commit may create a new `git_commit_path` identity record for equal bytes, but
neither record is mutated.

The v2 record ID seed is the v8 seed with
`agent-canon.artifact-identity.v2\0` as its domain separator. Packet imports
require `schema_version=2`. Every other v8 byte-read, SHA256, Git-blob, stable
`fstat`, structured import, and pre-dispatch readback predicate remains exact.

Stable generic-source failures:

- `artifact_identity:source_binding_kind_invalid`
- `artifact_identity:external_source_binding_forbidden`
- `artifact_identity:source_binding_null_rule_mismatch`
- retained v8 content/path/mode/blob/import/readback failures

### Immutable `TerminalResumeIntent`

The intent is created from current L, the exact prior locator, terminal
observation, current candidate/frame-independent review context, and owner
evidence.

```json
{
  "schema": "agent-canon.terminal-resume-intent.v1",
  "schema_version": 1,
  "resume_intent_id": "<deterministic intent ID>",
  "aggregate_identity": "<aggregate identity>",
  "review_lineage_id": "<review lineage ID>",
  "review_request_id": "<review request ID>",
  "review_context_id": "<review context ID>",
  "reviewer_assignment_id": "<reviewer assignment ID>",
  "reviewer_lineage_id": "<reviewer lineage ID>",
  "candidate_id": "<current candidate ID>",
  "candidate_revision": 1,
  "candidate_body_sha256": "<current candidate hash>",
  "dispatch_attempt": 1,
  "resume_mode": "provider_resume_same_runtime",
  "prior_locator": {
    "runtime_provider": "codex",
    "parent_runtime_agent_id": "<parent runtime ID>",
    "nested_runtime_agent_id": "<prior reviewer runtime ID>",
    "team_manifest_role_instance_ref": "team_manifest.yaml#<exact reviewer row>",
    "dispatch_receipt_path": "<prior receipt path>",
    "dispatch_receipt_sha256": "<prior receipt SHA256>",
    "last_review_frame_id": "<prior frame ID>",
    "last_observed_status": "completed",
    "last_observed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "locator_body_sha256": "<64 lowercase hex>"
  },
  "terminal_observation_identity": {
    "identity_record_id": "<artifact identity v2 record ID>",
    "identity_record_body_sha256": "<record body hash>"
  },
  "terminal_observation_body_sha256": "<canonical observation body hash>",
  "same_context_fingerprint": "<v8 stable context hash>",
  "request_clause_ids_sha256": "<ordered clause-array hash>",
  "fixed_source_packet_sha256": "<current source-packet hash>",
  "acceptance_identity_sha256": "<current acceptance hash>",
  "writer_identity_sha256": "<current writer identity hash>",
  "owner_role_id": "manager",
  "owner_runtime_agent_id": "<parent runtime ID>",
  "owner_surface_refs": [],
  "owner_surface_refs_sha256": "<ordered owner-ref array hash>",
  "intent_order_index": 1,
  "created_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "resume_intent_body_sha256": "<64 lowercase hex>"
}
```

Closed values:

- `resume_mode` is exactly `provider_resume_same_runtime` or
  `owner_selected_replacement_runtime`;
- prior terminal status is exactly `completed`, `errored`, or `shutdown`;
- timeout, missing, ambiguous, foreign, or stale runtime observations remain
  non-authoritative; and
- owner surfaces and equality hashes retain v8 definitions.

Intent ID seed:

```text
agent-canon.terminal-resume-intent.v1\0
aggregate-identity=<aggregate identity UTF-8>\0
review-lineage-id=<review lineage ID UTF-8>\0
reviewer-assignment-id=<assignment ID UTF-8>\0
candidate-id=<candidate ID UTF-8>\0
candidate-revision=<16 lowercase hex>\0
dispatch-attempt=<8 lowercase hex>\0
resume-mode=<legal mode UTF-8>\0
prior-runtime-agent-id=<prior runtime ID UTF-8>\0
terminal-observation-body-sha256=<64 lowercase hex>\0
same-context-fingerprint=<64 lowercase hex>\0
owner-surface-refs-sha256=<64 lowercase hex>\0
end\0
```

The range includes every shown NUL and no later byte.

```text
resume_intent_id =
  w2-review-resume-intent:<SHA256(exact seed bytes)>
```

`resume_intent_body_sha256` hashes RFC 8785 canonical JSON bytes with only that
field omitted. The intent contains no frame/event/binding identity.

### `AutomaticReviewFrame v3`

The retained v8 frame key set changes only as follows:

- schema becomes `agent-canon.automatic-review-frame.v3`;
- schema version becomes `3`;
- v8 `resume_transition` is removed; and
- one `resume_intent_ref` field is added.

First dispatch and live exact-instance continuation use:

```json
{
  "resume_intent_ref": null
}
```

Terminal same-context dispatch uses:

```json
{
  "resume_intent_ref": {
    "resume_intent_id": "<already durable intent ID>",
    "resume_intent_body_sha256": "<already durable intent body hash>"
  }
}
```

The frame body hash covers the intent ref. Frame ID remains the v8
lineage/candidate-revision/dispatch-attempt ID and therefore does not require an
event or binding identity. The four-field handoff remains exactly `objective`,
`owner_unit`, `fixed_source_packet`, and `acceptance_identity`.

Frame validation rereads the intent and requires current candidate, attempt,
assignment, context, source-packet, acceptance, writer, owner, and terminal
observation equality. There is no `expected_event_id`, replacement-authority
path/hash, event seed, binding ref, or pointer ref.

### Immutable `TerminalResumeEvent v2`

The event is created only after dispatch has returned and its local receipt
bytes have a durable artifact-identity v2 record.

```json
{
  "schema": "agent-canon.terminal-resume-event.v2",
  "schema_version": 2,
  "resume_event_id": "<deterministic event ID>",
  "event_kind": "terminal_resume_dispatch_observed",
  "aggregate_identity": "<aggregate identity>",
  "resume_intent_id": "<intent ID>",
  "resume_intent_body_sha256": "<intent body hash>",
  "review_frame_id": "<frame ID>",
  "review_frame_body_sha256": "<frame body hash>",
  "candidate_id": "<current candidate ID>",
  "candidate_body_sha256": "<current candidate hash>",
  "dispatch_attempt": 1,
  "resume_mode": "provider_resume_same_runtime",
  "observed_result": {
    "runtime_action": "resumed",
    "runtime_provider": "codex",
    "parent_runtime_agent_id": "<parent runtime ID>",
    "nested_runtime_agent_id": "<observed reviewer runtime ID>",
    "team_manifest_role_instance_ref": "team_manifest.yaml#<same reviewer row>",
    "role_id": "change_reviewer",
    "agent_type": "diff_triage_reviewer",
    "reviewer_assignment_id": "<same assignment ID>",
    "reviewer_lineage_id": "<same reviewer lineage ID>",
    "write_policy": "artifacts_only",
    "local_receipt_identity_record_id": "<artifact identity v2 ID>",
    "local_receipt_identity_record_body_sha256": "<record body hash>"
  },
  "same_context_fingerprint": "<same intent hash field>",
  "proposed_from_review_state": "dispatch_pending",
  "proposed_to_review_state": "dispatched",
  "event_order_index": 1,
  "observed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "resume_event_body_sha256": "<64 lowercase hex>"
}
```

Mode equality remains exact:

- resume mode requires observed runtime ID equals the prior intent locator ID
  and `runtime_action="resumed"`;
- replacement mode requires a different runtime ID and
  `runtime_action="spawned"`; and
- both require unchanged parent, team row, role, agent type, assignment,
  reviewer lineage, context, candidate, source packet, acceptance, writer
  identity, and reviewer/writer/parent separation.

Event ID seed:

```text
agent-canon.terminal-resume-event.v2\0
resume-intent-id=<intent ID UTF-8>\0
review-frame-id=<frame ID UTF-8>\0
candidate-id=<candidate ID UTF-8>\0
dispatch-attempt=<8 lowercase hex>\0
runtime-action=<resumed or spawned UTF-8>\0
result-runtime-agent-id=<observed runtime ID UTF-8>\0
local-receipt-identity-record-id=<identity record ID UTF-8>\0
local-receipt-identity-record-body-sha256=<64 lowercase hex>\0
event-order-index=<16 lowercase hex>\0
end\0
```

The event body hash uses RFC 8785 with only its own hash omitted. The event
contains no external-binding/current-pointer identity. Its proposed state is
not current authority until a later binding and pointer transaction succeeds.

### Exact `ExternalArtifactBindingEvent`

One schema binds local immutable event/receipt bytes to authoritative external
provider identity:

```json
{
  "schema": "agent-canon.external-artifact-binding-event.v1",
  "schema_version": 1,
  "external_binding_event_id": "<deterministic binding ID>",
  "binding_kind": "reviewer_resume_dispatch",
  "aggregate_identity": "<aggregate identity>",
  "resume_intent_id": "<intent ID>",
  "resume_intent_body_sha256": "<intent body hash>",
  "review_frame_id": "<frame ID>",
  "review_frame_body_sha256": "<frame body hash>",
  "resume_event_id": "<event ID>",
  "resume_event_body_sha256": "<event body hash>",
  "resume_event_artifact_identity_record_id": "<event artifact identity v2 ID>",
  "resume_event_artifact_identity_record_body_sha256": "<record body hash>",
  "publication_authority_id": null,
  "publication_authority_body_sha256": null,
  "candidate_id": null,
  "candidate_body_sha256": null,
  "provider_kind": "codex_runtime",
  "provider_instance_id": "<provider installation/session namespace ID>",
  "provider_account_id": null,
  "provider_repository_id": null,
  "external_object_kind": "nested_agent_dispatch",
  "external_object_id": "<provider object ID>",
  "external_object_version": "<provider monotone version or receipt sequence>",
  "external_object_oid": null,
  "external_parent_object_id": "<parent runtime agent ID>",
  "provider_receipt_id": "<provider receipt ID>",
  "provider_receipt_version": "<provider receipt version>",
  "receipt_artifact_identity_record_id": "<local receipt identity v2 ID>",
  "receipt_artifact_identity_record_body_sha256": "<record body hash>",
  "provider_readback_identity_sha256": "<canonical provider readback hash>",
  "equality_inputs": {
    "event_observed_object_id": "<observed runtime ID>",
    "event_observed_parent_object_id": "<observed parent runtime ID>",
    "event_local_receipt_identity_record_id": "<event receipt identity ID>",
    "event_local_receipt_identity_record_body_sha256": "<event receipt record hash>",
    "expected_candidate_id": "<current candidate ID>",
    "expected_candidate_body_sha256": "<current candidate hash>",
    "expected_publication_authority_id": null,
    "expected_publication_authority_body_sha256": null
  },
  "binding_order_index": 1,
  "bound_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "external_binding_event_body_sha256": "<64 lowercase hex>"
}
```

Allowed `binding_kind`/provider combinations are exactly:

| `binding_kind` | `provider_kind` | `external_object_kind` |
| --- | --- | --- |
| `reviewer_resume_dispatch` | `codex_runtime` | `nested_agent_dispatch` |
| `github_publication_receipt` | `github` | `pull_request_head`, `review`, or `ref_update` |

Null rules:

| Field | `codex_runtime` | `github` |
| --- | --- | --- |
| `provider_instance_id` | non-null | non-null |
| `provider_account_id` | null | non-null |
| `provider_repository_id` | null | non-null canonical repository ID |
| `external_object_id` | non-null runtime object ID | non-null provider object ID |
| `external_object_version` | non-null provider sequence | non-null provider version/ETag |
| `external_object_oid` | null | non-null 40-lowercase Git OID |
| `external_parent_object_id` | non-null parent runtime ID | non-null PR/repository parent object ID |
| receipt identity record fields | non-null | non-null |

For `github_publication_receipt`, all eight resume intent/frame/event identity
fields are `null`; the four publication/candidate fields are non-null. For
`reviewer_resume_dispatch`, all eight resume identity fields are non-null and
the four publication/candidate fields are `null`.

`equality_inputs` null rules are:

| Input group | Reviewer binding | GitHub binding |
| --- | --- | --- |
| event observed object/parent and local receipt fields | non-null | null |
| expected candidate ID/hash | non-null, derived through the resume chain | non-null |
| expected publication authority ID/hash | null | non-null |

External binding ID seed:

```text
agent-canon.external-artifact-binding-event.v1\0
binding-kind=<binding kind UTF-8>\0
aggregate-identity=<aggregate identity UTF-8>\0
resume-intent-id=<intent ID or null UTF-8>\0
resume-intent-body-sha256=<64 lowercase hex or null UTF-8>\0
review-frame-id=<frame ID or null UTF-8>\0
review-frame-body-sha256=<64 lowercase hex or null UTF-8>\0
resume-event-id=<event ID or null UTF-8>\0
resume-event-body-sha256=<64 lowercase hex or null UTF-8>\0
resume-event-artifact-identity-record-id=<identity record ID or null UTF-8>\0
resume-event-artifact-identity-record-body-sha256=<64 lowercase hex or null UTF-8>\0
publication-authority-id=<authority ID or null UTF-8>\0
publication-authority-body-sha256=<64 lowercase hex or null UTF-8>\0
candidate-id=<candidate ID or null UTF-8>\0
candidate-body-sha256=<64 lowercase hex or null UTF-8>\0
provider-kind=<provider kind UTF-8>\0
provider-instance-id=<provider instance ID UTF-8>\0
provider-account-id=<provider account ID or null UTF-8>\0
provider-repository-id=<provider repository ID or null UTF-8>\0
external-object-kind=<object kind UTF-8>\0
external-object-id=<object ID UTF-8>\0
external-object-version=<object version UTF-8>\0
external-object-oid=<40 lowercase hex or null UTF-8>\0
external-parent-object-id=<parent object ID UTF-8>\0
provider-receipt-id=<receipt ID UTF-8>\0
provider-receipt-version=<receipt version UTF-8>\0
receipt-identity-record-id=<identity record ID UTF-8>\0
receipt-identity-record-body-sha256=<64 lowercase hex>\0
provider-readback-identity-sha256=<64 lowercase hex>\0
binding-order-index=<16 lowercase hex>\0
end\0
```

The range includes every shown NUL and no later byte.

```text
external_binding_event_id =
  w2-external-artifact-binding:<SHA256(exact seed bytes)>
```

`external_binding_event_body_sha256` hashes RFC 8785 canonical JSON bytes with
only that field omitted. The binding event contains no current-pointer ID/hash.

`provider_readback_identity_sha256` is SHA256 over RFC 8785 canonical JSON
bytes of exactly:

```json
{
  "provider_kind": "<provider kind>",
  "provider_instance_id": "<provider instance ID>",
  "provider_account_id": "<value or null>",
  "provider_repository_id": "<value or null>",
  "external_object_kind": "<object kind>",
  "external_object_id": "<object ID>",
  "external_object_version": "<object version>",
  "external_object_oid": "<40 lowercase Git OID or null>",
  "external_parent_object_id": "<parent object ID>",
  "provider_receipt_id": "<receipt ID>",
  "provider_receipt_version": "<receipt version>"
}
```

The provider adapter constructs this typed object directly from the provider
API response. Free-form logs, PR prose, labels, reviewer summaries, and HTTP
text are not identity.

Equality predicates:

- reviewer binding provider object ID equals event observed runtime ID;
- reviewer parent object equals event parent runtime ID;
- receipt ID/version and local receipt identity equal event receipt fields;
- intent/frame/event body hashes and current candidate/context all match;
- GitHub binding object OID equals current candidate/head and frozen
  publication authority;
- provider repository equals the frozen repository identity;
- all null rules and binding-kind/provider-kind combinations match; and
- provider readback is repeated immediately before pointer/publication use.

The `equality_inputs` values are comparison operands, not stored success
booleans. Every consumer recomputes the predicates above from the referenced
immutable bodies and current L/provider readback.

### Current pointer CAS projection

The DAG ends in one aggregate update, not another forward-referenced immutable
artifact. The CAS input is:

```json
{
  "schema": "agent-canon.review-resume-current-pointer-update.v1",
  "schema_version": 1,
  "aggregate_identity": "<aggregate identity>",
  "expected_current_pointer_fingerprint": "<64 lowercase hex>",
  "current_resume_intent_id": "<intent ID>",
  "current_resume_intent_body_sha256": "<intent body hash>",
  "current_review_frame_id": "<frame ID>",
  "current_review_frame_body_sha256": "<frame body hash>",
  "current_resume_event_id": "<event ID>",
  "current_resume_event_body_sha256": "<event body hash>",
  "current_external_binding_event_id": "<binding ID>",
  "current_external_binding_event_body_sha256": "<binding body hash>",
  "current_reviewer_locator_body_sha256": "<locator projection hash>",
  "current_review_state": "dispatched",
  "new_current_pointer_fingerprint": "<64 lowercase hex>"
}
```

This transaction body is a ledger write input and contains no ID/hash for
itself. `expected_current_pointer_fingerprint` is SHA256 over RFC 8785 canonical
JSON bytes of the complete pre-intent current review-pointer projection.
`new_current_pointer_fingerprint` is SHA256 over RFC 8785 canonical JSON bytes
of an object containing exactly the eight new ID/hash fields, locator hash, and
state.

The update succeeds only if the aggregate still has the expected fingerprint,
candidate, attempt, and `dispatch_pending` state. Pointer readback recomputes
the new fingerprint and traverses every referenced body hash to the already
durable binding, event, frame, and intent.

### State write, fsync, and readback order

The exact durable sequence is:

1. lock L; verify current candidate, `dispatch_pending`, prior locator, terminal
   observation, context, and attempt;
2. append `TerminalResumeIntent`; write/fsync/rename/fsync-directory through
   the retained v8 ledger protocol; reread and verify intent ID/body hash;
3. create and append frame v3 referencing only that intent; durable write and
   reread frame ID/body hash;
4. dispatch using the frame's unchanged four-field handoff;
5. materialize local dispatch receipt as artifact identity v2;
6. append `TerminalResumeEvent v2` referencing intent/frame/local receipt;
   durable write and reread event ID/body hash;
7. materialize the durable resume-event bytes as artifact identity v2, query
   the external provider by owner API, materialize canonical provider readback,
   and append `ExternalArtifactBindingEvent v1`; durable write and reread
   binding ID/body hash;
8. reacquire/retain the ledger lock and CAS the aggregate from the exact prior
   pointer fingerprint to:
   - `current_resume_intent_id`;
   - `current_review_frame_id`;
   - `current_resume_event_id`;
   - `current_external_binding_event_id`;
   - current reviewer locator derived from the event; and
   - `current_review_state="dispatched"`;
9. write/fsync/rename/fsync-directory the aggregate transaction; and
10. reread L plus provider state and verify the complete intent/frame/event/
    binding/pointer chain and current reviewer identity.

No pointer or `dispatched` state changes in steps 2-7. A crash after any durable
node resumes from that node:

- intent only: recreate/verify the deterministic frame;
- frame only: inspect provider dispatch state; do not blindly dispatch twice;
- event only: create/verify external binding;
- binding only: retry the exact pointer CAS;
- pointer write uncertainty: reread L and accept only exact complete-chain
  equality.

Unknown provider dispatch state is typed blocked with durable evidence; it is
not resolved by a fresh reviewer.

### Stable failures and negative oracles

One-way DAG failures:

- `review_resume_dag:intent_future_reference`
- `review_resume_dag:frame_future_reference`
- `review_resume_dag:event_future_reference`
- `review_resume_dag:binding_future_pointer_reference`
- `review_resume_dag:id_seed_contains_future_object`
- `review_resume_dag:write_order_violation`
- `review_resume_dag:readback_order_violation`
- `review_resume_dag:pointer_advanced_before_binding`
- `review_resume_dag:state_advanced_before_binding`
- `review_resume_dag:partial_chain_current`
- `review_resume_dag:provider_dispatch_state_unknown`

External binding failures:

- `external_artifact_binding:schema_mismatch`
- `external_artifact_binding:provider_kind_mismatch`
- `external_artifact_binding:object_kind_mismatch`
- `external_artifact_binding:null_rule_mismatch`
- `external_artifact_binding:provider_object_mismatch`
- `external_artifact_binding:provider_parent_mismatch`
- `external_artifact_binding:receipt_identity_mismatch`
- `external_artifact_binding:provider_readback_mismatch`
- `external_artifact_binding:chain_identity_mismatch`
- `external_artifact_binding:candidate_or_authority_stale`
- `external_artifact_binding:event_id_mismatch`
- `external_artifact_binding:event_body_hash_mismatch`
- `external_artifact_binding:replay_conflict`
- `external_artifact_binding:readback_changed`

Every failure preserves the last fully durable chain, keeps publication locked,
and creates no approval, current pointer, fresh reviewer, or cleanup authority.

## Rejected Alternatives

- Frame-precomputed event IDs are rejected because the frame would identify a
  future object.
- A pre-dispatch authority receipt that hashes frame bytes while the frame
  hashes the receipt is rejected as cyclic.
- Mutable placeholder events completed after provider dispatch are rejected
  because history would not be immutable.
- Advancing `dispatched` before external provider binding is rejected because
  local observation alone is not external authority.
- Keeping `external_immutable_receipt` in generic source binding is rejected
  because it conflates byte provenance with provider semantics.
- Embedding provider IDs in artifact identity v2 is rejected; provider identity
  belongs only to the external binding event.
- A compatibility selector for v8 frame/event/source-binding schemas is
  rejected.

## Abstract Design Frame

The replaceable unit remains `completion_authority`, with two simplified
sub-responsibilities:

1. `ReviewerResumeChain` creates immutable intent, frame, event, binding, and
   current projection in dependency order; and
2. `ExternalArtifactBinder` binds local artifact bytes to typed provider
   object/receipt identity without changing generic byte identity.

Required invariants:

- L remains sole authority.
- Stored views remain pure fingerprint-bound projections.
- Current pointers reference only a complete externally bound chain.
- No immutable object identifies a future object.
- Generic artifact identity proves bytes/source only.
- External binding proves provider/object/receipt equality only.
- Reviewer remains distinct from writer and parent.
- Fresh/self-review/prompt/keyword/CI bypass remains forbidden.
- v8 exact candidate-OID publication and dirty-checkout preservation remain.
- No object hashes its own complete file or containing Git identity.

## Implementation Source Packet

### Bound predecessor and request evidence

The v8 commit/tree/artifact identities in `Normative Incorporation Of v8` are
the exact predecessor packet. The v9 review input is the explicit user clause
packet:

```text
review_input_kind=explicit_user_simplification_packet
finding_count=2
finding_1=V9-R1
finding_2=V9-R2
```

No separate review artifact was supplied. No path/hash/blob is invented.

### Mandatory later implementation reads

1. `agents/COMMUNICATION_PROTOCOL.md`
2. `agents/canonical/CODEX_WORKFLOW.md`
3. `agents/canonical/CODEX_SUBAGENTS.md`
4. `agents/task_catalog.yaml`
5. `agents/agents_config.json`
6. `.codex/agents/diff_triage_reviewer.toml`
7. `.codex/agents/ship_reviewer.toml`
8. future `tools/agent_tools/artifact_identity.py`
9. future `tools/agent_tools/external_artifact_binding.py`
10. future `tools/agent_tools/review_dispatch.py`
11. `tools/agent_tools/agent_team.py`
12. `tools/agent_tools/workflow_monitor.py`
13. `tools/agent_tools/github_publish.py`
14. future `tools/agent_tools/publication_integrator.py`
15. `tools/agent_tools/report_artifact_checks.py`
16. `tools/agent_tools/task_close.py`
17. future `tests/agent_tools/test_artifact_identity.py`
18. future `tests/agent_tools/test_external_artifact_binding.py`
19. future `tests/agent_tools/test_review_dispatch.py`
20. `tests/agent_tools/test_workflow_monitor.py`
21. `tests/agent_tools/test_github_publish.py`
22. future `tests/agent_tools/test_publication_integrator.py`
23. `tests/agent_tools/test_report_artifact_checks.py`
24. `tests/agent_tools/test_task_start_and_close.py`

Implementation remains blocked until independent v9 fixed-byte approval.

## Design Side-Effect Map

Every row is future implementation scope only.

| Path | Exact future change | Clause | Gate |
| --- | --- | --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md` | replace cyclic resume schema with intent/frame/event/binding schemas; define artifact identity v2 | both | schema-owner review |
| `agents/canonical/CODEX_WORKFLOW.md` | require five-stage DAG and pointer/state advance only after binding readback | V9-R1 | workflow-owner review |
| `agents/canonical/CODEX_SUBAGENTS.md` | route terminal reviewer through intent-first chain; retain terminal and no-return semantics | V9-R1 | lifecycle review |
| `agents/task_catalog.yaml`, `agents/agents_config.json`, reviewer TOMLs | retain assignment/role/agent/read-only identity across frame/event/binding | V9-R1 | runtime alignment |
| future `artifact_identity.py` | emit v2 with only Git/filesystem source variants | V9-R2 | artifact identity tests |
| future `external_artifact_binding.py` | query provider, enforce null/equality rules, emit one binding event | V9-R2 | external binding tests |
| future `review_dispatch.py` | write/read intent, frame, event, binding, then pointer; no future refs | V9-R1 | review dispatch tests |
| `agent_team.py` | derive unchanged reviewer assignment; no identity override | V9-R1 | team tests |
| `workflow_monitor.py` | record each durable stage and exact blocked/crash-resume state | V9-R1 | monitor tests |
| `github_publish.py`, future `publication_integrator.py` | use GitHub external binding variant before PR/publication pointer or CAS use | V9-R2 | publication tests |
| `report_artifact_checks.py`, `task_close.py` | reject partial/cyclic chains, invalid source kind, unbound external receipt, or early pointer | both | report/closeout tests |
| `documents/conventions/REVIEW_PROCESS.md`, review/closeout templates | review DAG order, external null rules, and all v8 non-regressions | both | independent review |

OOP/SOLID and implementation/test execution remain pending.

## Dependency-Header Closure

The retained v8 dependency pairs remain exact. v9 adds these future pairs:

| Owner/consumer line | Exact inverse line |
| --- | --- |
| `agents/COMMUNICATION_PROTOCOL.md`: `downstream implementation ../tools/agent_tools/external_artifact_binding.py binds canonical local artifacts to external provider identities` | `tools/agent_tools/external_artifact_binding.py`: `upstream implementation ../../agents/COMMUNICATION_PROTOCOL.md owns external artifact binding schemas` |
| `tools/agent_tools/review_dispatch.py`: `upstream implementation ./external_artifact_binding.py binds reviewer resume dispatch receipts` | `tools/agent_tools/external_artifact_binding.py`: `downstream implementation ./review_dispatch.py consumes reviewer resume external bindings` |
| `tools/agent_tools/github_publish.py`: `upstream implementation ./external_artifact_binding.py binds GitHub publication receipts` | `tools/agent_tools/external_artifact_binding.py`: `downstream implementation ./github_publish.py consumes GitHub publication external bindings` |
| `tools/agent_tools/publication_integrator.py`: `upstream implementation ./external_artifact_binding.py verifies provider-bound publication receipts` | `tools/agent_tools/external_artifact_binding.py`: `downstream implementation ./publication_integrator.py gates publication on external bindings` |
| `tools/agent_tools/external_artifact_binding.py`: `downstream implementation ../../tests/agent_tools/test_external_artifact_binding.py validates provider, object, receipt, null, equality, and replay contracts` | `tests/agent_tools/test_external_artifact_binding.py`: `upstream implementation ../../tools/agent_tools/external_artifact_binding.py implements external artifact binding` |

`artifact_identity.py` retains its v8 owner/consumer pairs, with schema v2.
No durable header points to this v9 report.

## Design-to-Implementation Trace

| Slice | Responsibility | Exact paths | Oracle |
| --- | --- | --- | --- |
| V9-S1 Intent | freeze current terminal/context/owner facts without future identity | protocol, review dispatcher, ledger | intent key/hash/future-ref negatives |
| V9-S2 Frame | route exact reviewer using only durable intent | protocol, review dispatcher, team owner | frame v3 and four-field handoff negatives |
| V9-S3 Event | bind observed dispatch result and local receipt after frame | review dispatcher, artifact identity, monitor | mode/result/receipt/event ID negatives |
| V9-S4 External binding | bind provider/object/receipt identity after event | external binder, runtime/GitHub adapters | null/equality/readback/replay negatives |
| V9-S5 Pointer | publish complete chain as current only after binding | ledger, workflow monitor, report checks, task close | early/partial pointer and crash-resume negatives |
| V9-S6 Generic source | restrict byte source to Git commit or immutable file | artifact identity, packet consumers | invalid external source kind/null-rule tests |
| V9-S7 Non-regression | preserve every v8 acceptance predicate | all v8 owner/consumer/test paths | independent full v8 recheck |

## Exact Acceptance Predicates

### V9-R1 one-way immutable reviewer-resume DAG

Pass if and only if:

1. the only construction order is intent, frame, event, external binding,
   current pointer;
2. intent references no later object;
3. frame references only intent among new DAG objects;
4. event references intent/frame and already materialized local receipt only;
5. external binding references intent/frame/event and provider readback only;
6. no object contains a current-pointer ID/hash;
7. every ID seed and body hash contains only existing predecessors and own
   non-hash fields;
8. intent/frame/event/binding are separately immutable, durable, and read back
   before the next stage;
9. state remains `dispatch_pending` through binding durability;
10. one later aggregate CAS advances all current chain pointers, reviewer
    locator, and state to `dispatched`;
11. crash recovery resumes from the last exact durable node without duplicate
    blind dispatch or fresh reviewer;
12. post-pointer readback proves the complete chain and provider state;
13. partial, cyclic, future-referencing, early-state, or unknown-provider state
    fails typed; and
14. reviewer independence, same context, assignment, source packet,
    acceptance, and no prompt/self-review bypass remain exact.

### V9-R2 exact external artifact binding

Pass if and only if:

1. artifact identity schema v2 allows exactly `git_commit_path` and
   `filesystem_immutable`;
2. `external_immutable_receipt` is rejected;
3. all source-binding null rules are exact;
4. external receipt bytes receive a local artifact identity v2 record before
   provider binding;
5. one external binding event schema owns provider/object/receipt semantics;
6. binding-kind/provider/object combinations are closed;
7. codex/GitHub null rules are exhaustive;
8. binding ID seed and RFC 8785 body hash are exact and non-self-referential;
9. reviewer provider object/parent/receipt equals event observations;
10. GitHub repository/object OID/receipt equals candidate and frozen
    publication authority;
11. provider readback is canonical and repeated before pointer/publication use;
12. no external prose, labels, logs, summaries, or free-text hashes have
    identity authority;
13. mismatch, null error, stale authority, replay, or readback change fails
    typed; and
14. external binding creates no approval or current state by itself.

### Preserved v8 acceptance

Pass if and only if an independent reviewer reconfirms all v8 acceptance
sections, with only the exact V9-R1/V9-R2 substitutions:

- V8-I1;
- V8-I2 local-byte materialization/import/readback;
- V8-D1;
- V8-L1 semantic reviewer-resume requirements;
- V8-P1;
- V6-R1;
- V6-R2;
- V7-A1;
- preserved v6 contracts; and
- all v8 public negative plans.

## Public Typed Negative-Test Plan

| Negative | Public boundary | Typed result |
| --- | --- | --- |
| intent contains frame/event/binding/pointer identity | intent validator | `review_resume_dag:intent_future_reference` |
| frame contains event/binding/pointer identity | frame validator | `review_resume_dag:frame_future_reference` |
| event contains binding/pointer identity | event validator | `review_resume_dag:event_future_reference` |
| binding contains pointer identity | binding validator | `review_resume_dag:binding_future_pointer_reference` |
| any seed hashes a future object | canonical serializer | `review_resume_dag:id_seed_contains_future_object` |
| frame is written before intent readback | ledger writer | `review_resume_dag:write_order_violation` |
| state/pointer advances before binding readback | ledger/closeout | early-state/pointer failure |
| crash after frame causes blind second dispatch | review dispatcher | `review_resume_dag:provider_dispatch_state_unknown` |
| generic source kind is external receipt | artifact identity | `artifact_identity:external_source_binding_forbidden` |
| source-binding null fields violate table | artifact identity | `artifact_identity:source_binding_null_rule_mismatch` |
| provider kind/object kind combination differs | external binder | provider/object-kind mismatch |
| codex/GitHub null field differs | external binder | `external_artifact_binding:null_rule_mismatch` |
| runtime provider object differs from event result | external binder | provider-object mismatch |
| parent runtime differs | external binder | provider-parent mismatch |
| provider receipt differs from local receipt identity | external binder | receipt-identity mismatch |
| GitHub object OID/repository differs from candidate/authority | publication gate | stale/chain mismatch |
| duplicate binding ID has different bytes | external binder | `external_artifact_binding:replay_conflict` |
| provider readback changes before pointer/CAS | pointer/publication gate | `external_artifact_binding:readback_changed` |
| external binding alone is treated as approval | publication gate | publication remains locked |

No hand-written pass artifact satisfies any oracle.

## Review And Validation Contract

The independent v9 reviewer must verify:

1. exact v8 predecessor identities;
2. exact five-node dependency direction;
3. absence of every future-object reference;
4. intent/frame/event/binding schemas and ID/hash byte ranges;
5. state write/fsync/readback and crash-resume order;
6. artifact identity v2 source-kind and null rules;
7. external binding provider/object/receipt schema, variant null rules, ID seed,
   equality, and readback;
8. exact side-effect/dependency/test trace;
9. every V9-R1/V9-R2 negative oracle;
10. every v8 acceptance/non-regression predicate; and
11. exact design-only two-file commit scope.

Later implementation validation includes selected artifact-identity, external
binding, review-dispatch, monitor, GitHub, publication, report, and closeout
tests plus OOP/SOLID evidence and independent source-freeze review.

### Validation honesty

- `oop_readability=pending`
- `solid_evidence=pending`
- `formatter=pass:tools/bin/agent-canon_docs_format`
- `selected_non_python_static=pass:tools/bin/agent-canon_docs_check`
- `targeted_tests=pending`
- `python_execution=deferred_by_user`
- `ci=deferred_by_user`
- `dynamic_graph=deferred_by_user`
- `dependency_graph_execution=deferred_by_user`
- `implementation_authorization=blocked_until_independent_v9_design_approval`

No source, Python, test, CI, dynamic-graph, OOP, SOLID, or implementation result
is promoted to pass by this design. No file requires its own containing
commit/tree/blob/SHA, and no hand-written artifact may satisfy a completion
gate.
