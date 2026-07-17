# W2 Detailed-Design v13 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V13-P1,V13-O1,V13-C1
owner_unit=existing materializer-backed validation/review/publication contract
```

Review only the exact v13 bytes identified below. This request authorizes no
source implementation, tests, owner documents, hooks, Python, CI, dynamic
graph, validation execution, review dispatch, publication, compatibility
route, receipt ledger, or hand-written pass artifact.

Reviewer identity must differ from the design writer. Parent remains
monitor/integrator. REVISE returns findings to the retained same
writer/reviewer lineage and evaluates the repaired successor. It never selects
an older candidate or a fresh/self reviewer.

This request contains no identity for its own bytes, Git blob, containing
commit, tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v13.md
target_size_bytes=58192
target_sha256=3ddb21cff86dc947bebedf8e5b35bd9f799ebd6fa4d100e0637a3299fc2cb9b8
target_git_blob=ab14becc1d546f661d8c1b4f2e95ac9aef493f39
target_encoding=UTF-8
target_bom=absent
target_line_endings=LF
target_identity_authority=canonical_tool_readback
```

Independently recompute size, SHA256, and Git blob before content review.
Mismatch is:

`review_target_identity_mismatch`.

Do not review reformatted, summarized, copied, regenerated, or
chat-transcribed bytes.

## Bound v12 Predecessor

```text
predecessor_commit=47a4bb0516d7d320511c4671970a8b23cef0211f
predecessor_tree=5cd321deea02bf7c87140db71b4315d8c565678a
predecessor_parent=5a842b7f55da8237d81fa5a96c13f7f278245d1d
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v12.md
predecessor_design_size_bytes=68762
predecessor_design_sha256=900214147d7a1216729237296487fba1ad376d24894047cda71b6887aef1daab
predecessor_design_git_blob=0b228053db2dc071781a459d94fb799fb79ef664
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v12.md
predecessor_request_size_bytes=12490
predecessor_request_sha256=8e0d3e7832e6d594df20aaf745b37df90c1dfb1831921bbd04b6eefeb78ef248
predecessor_request_git_blob=1999526ad310832d7fef735f1eaf13eec635067e
```

v13 is an append-only delta over this exact v12 packet and all incorporated
v11-v8 contracts.

## Bound Review Input

```text
review_input_kind=explicit_user_v13_design_closure
durable_decision_artifact=not_supplied
finding_count=3
finding_1=V13-P1
finding_2=V13-O1
finding_3=V13-C1
```

Do not invent a review artifact, hash, blob, or decision.

## Required V13-P1 Recheck

Verify:

- every public projection resolver returns exactly one
  `ProjectionResolution v1` envelope;
- projection kinds and result kinds are closed;
- returned projection requires non-null matching v2 projection and null
  no-projection;
- no-projection requires null projection and one exact `NoProjection v1`;
- no-projection reason/null table has exactly the validation, review, and
  publication rows;
- no-projection exists only when the immediate canonical subject is absent;
- pending, failed, deferred, not-applicable, missing review context, missing
  approval, and missing publication authority use returned negative
  projections as specified;
- malformed, contradictory, foreign, stale-pointer, schema, hash, or owner
  evidence is never converted to absence;
- no-projection has no ID, body hash, outcome, failure set, eligibility,
  approval, or gate authority;
- validation result v2 has one exact key set and five exact outcome/null rows;
- review eligibility v2 has one exact key set and six exact outcome/null rows;
- publication eligibility v2 has one exact key set and six exact outcome/null
  rows;
- resolver precedence fixes every nullable field shape;
- generic `ineligible` no longer exists;
- all common non-null fields remain non-null in returned projections;
- nullable strings, integers, objects, arrays, hashes, and OIDs use the exact
  v13 typed seed encoding;
- non-null object/array hashes use exact RFC 8785 bytes and nested null members
  use canonical JSON `null`;
- omitted, empty-string, bare-null text, zero-hash, or unframed values are
  forbidden;
- validation result seed includes exact locator, aggregate, candidate, route,
  attempt, artifact, producer, outcome, and failure-code terms in exact order;
- the formula
  `validation-result:<SHA256(exact expanded seed bytes)>` is complete;
- review and publication seeds use the exact nullable fields/order;
- body hashes omit only their own body-hash field;
- v1 projection schemas are rejected without compatibility selection; and
- every no-projection/outcome/null/seed/body mismatch has a typed public
  negative.

## Required V13-O1 Recheck

Verify:

- one deterministic owner-chain ID binds locator, logical key, attempt, begin
  transaction, pending event, artifact ID/root, and frozen owner tool;
- all owner-chain seed fields and order are exact and non-null;
- stable attempt-lock path remains the v12 deterministic path;
- lock body has one exact complete key set and body hash;
- lock body is stable across retries and contains no mutable PID, timestamp, or
  nonce;
- live ownership is the retained exclusive OS lock;
- manifest adds exact owner-chain, begin, pending, and lock refs;
- manifest does not reference later creation owner, terminal event, settlement,
  pointer, or projection;
- `creation_owner.json` has the exact v13 schema/key set;
- creation-owner record links the same locator/logical key/attempt/begin/
  pending/lock/artifact/manifest/owner tool;
- creation-owner ID seed and body hash are exact;
- creation-owner record does not contain its own complete-file SHA/blob or a
  future identity;
- settle transaction and terminal event externally bind creation-owner and
  manifest path/SHA/blob;
- artifact root has exactly the six sorted v13 leaves;
- complete-root reuse first regenerates and compares every owner-chain member;
- manifest owner fields equal creation-owner fields;
- lock body/path/file identity equals both;
- owner tool identity equals lock, manifest, creation owner, route, and frozen
  source;
- existing terminal/settlement evidence, when present, binds the same record;
- a root without creation owner is incomplete and not reusable as complete;
- exact missing-owner recovery is allowed only under the same valid lock/chain
  and exact raw/manifest bytes;
- live, foreign, corrupt, extra, mismatched, or differently owned roots are
  retained and never deleted, adopted, rebound, or repaired in place; and
- every chain/file/replay mismatch has a typed public negative.

## Required V13-C1 Recheck

Verify:

- VersionOutcome v2 has one exact key set for captured, unsupported, and
  failed;
- version outcome includes artifact ID and deterministic outcome ID;
- all three variant null rows for policy, argv/hash, termination, streams,
  normalization, and failure class are exact;
- observations and streams are present for every version variant;
- version ID seed uses canonical nullable JSON/string/object encoding;
- version body hash and exact termination union are complete;
- CommandOutcome v2 has one exact key set for executed and not-run;
- `kind`, `version_outcome_ref`, both observation refs, `termination`,
  `version_failure_ref`, streams, combined hash, complete, and body hash are
  present in both variants;
- executed has a captured/unsupported version ref, non-null termination, and
  null version-failure ref;
- executed spawn failure remains executed with
  `termination.kind=spawn_failed`;
- not-run has a failed version ref, null termination, non-null exact
  version-failure ref, two not-created streams, and `complete=false`;
- version-failure ref contains exact version outcome ID/hash, failure class,
  and failure-evidence hash;
- failure-evidence hash covers exact failed version termination, streams,
  normalization, and class;
- command body hash is exact;
- the only legal transitions are captured-to-executed,
  unsupported-to-executed, and failed-to-not-run;
- the other three rows are forbidden;
- command kind is derived from version kind, not caller text;
- version observation linkage remains 1-to-2 and command linkage 2-to-3;
- every illegal transition/null/ref/stream/complete/hash mismatch forces
  validation result fail with typed evidence; and
- no compatibility schema or test-only transition API exists.

## Required v12 C1 And Retained-Contract Recheck

Return an explicit result for:

- fixed canonical `.active_run` and baseline locator;
- exact locator schema/readback and workspace-only public APIs;
- zero public report root/directory, run ID, route, artifact, manifest, raw
  stream, projection, or receipt path override;
- deterministic artifact seed/root/lock path from v12;
- exactly three executable/module identity observations;
- repo/external module origin union;
- stream EOF-complete/capture-failed/not-created union;
- one materializer, one L, one current attempt, begin/settle CAS, and v7 crash
  recovery;
- linear validation-result to review-eligibility to publication-eligibility
  responsibility direction;
- v11 registered route/environment/command strength and no receipt ledger;
- v10 local event sole authority and external projection;
- v9 one-way review DAG;
- v8 automatic review, same-context lineage, artifact binding, candidate-OID
  publication, dirty-checkout protection, and expected-old-OID CAS;
- publication route inventory and no alternate direct merge/push route;
- immutable intent revision list and one current pointer;
- per-member source-event correspondence and group equality;
- D2/D3/F1/F2, freeze/topology, and five formatter statuses;
- no self/fresh review bypass, prompt/keyword side path, or CI-only inference;
- no compatibility/test-only API, durable dependency to run-local reports, or
  self-referential artifact; and
- every retained public negative oracle.

Only V13-P1, V13-O1, and V13-C1 may replace v12 text.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V13_P1=pass|fail
V13_O1=pass|fail
V13_C1=pass|fail
v12_C1_and_retained_contracts=pass|fail
implementation_authorization=blocked
reviewed_target_path=<exact target path>
reviewed_target_size_bytes=<recomputed size>
reviewed_target_sha256=<recomputed SHA256>
reviewed_target_git_blob=<recomputed Git blob>
reviewer_identity=<independent reviewer identity>
review_artifact_path=<external review artifact path>
```

APPROVE requires every result to pass. The review artifact must not contain its
own complete-file SHA, Git blob, containing commit, or tree. Those identities
are materialized externally after review bytes are fixed.

## Scope And Validation Boundary

The design-author commit must change exactly:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v13.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v13.md
```

Expected design-author validation:

```text
tools/bin/agent-canon docs format <exact two paths>
tools/bin/agent-canon docs check <exact two paths>
git diff --check -- <exact two paths>
Git size/SHA256/blob readback
```

Projection/no-projection execution, nullable-seed execution, creation-owner
replay, version-command transitions, OOP/SOLID, public negative tests, and
publication integration remain typed pending. Source implementation remains
blocked until this exact v13 target receives independent APPROVE.
