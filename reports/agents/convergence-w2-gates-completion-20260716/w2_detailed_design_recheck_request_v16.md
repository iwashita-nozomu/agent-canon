# W2 Detailed-Design v16 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V16-R1,V16-R2,V16-R3
owner_unit=missing-owner final publication concurrency algebra
```

Review only the exact v16 bytes identified below. This request authorizes no
source implementation, tests, owner documents, hooks, Python, CI, dynamic
graph, recovery execution, publication execution, review dispatch, new runner,
new ledger, compatibility path, cleanup, or hand-written pass artifact.

Reviewer identity must differ from the design writer. Parent remains
monitor/integrator. REVISE returns findings to the retained same
writer/reviewer lineage and evaluates only a repaired successor.

This request contains no identity for its own bytes, Git blob, containing
commit, tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v16.md
target_size_bytes=35482
target_sha256=cb4ca57b443ea795126a787e61ac34e3b164b3fb5a84d3601bcb7f994e0ca0d6
target_git_blob=9d8f22a21f13e04ccd71ce9bb7cac7e9323c075f
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

## Bound v15 Predecessor

```text
predecessor_commit=b24a2b9b7956b5eaf5b16144577870670dd4eec0
predecessor_tree=eaf91660889ce3f06e10a8786ddc8ab965349905
predecessor_parent=d82efcf6872cbda9d61f73f702c4057555aa8c77
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v15.md
predecessor_design_size_bytes=38823
predecessor_design_sha256=f80fc43e22584ebce29c2614e524708c82ef667d5b1fcfb613d756a9b93c2af4
predecessor_design_git_blob=7d655afb274a76373f7e479f1660dab40794ac6d
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v15.md
predecessor_request_size_bytes=12681
predecessor_request_sha256=c3526634ce1d7b09b2765c08892d8b2586b968f43e132d55119b8efbfec271df
predecessor_request_git_blob=8f98577bc8b5a70ba65c2210b5a6f97df809882a
```

v16 is an append-only delta over this exact v15 packet. v15 normatively
incorporates v14 `CommandOutcome v3`, v12 C1, and all retained v14-v8
contracts.

## Bound Review Input

```text
review_input_kind=explicit_user_v16_final_race_closure
durable_decision_artifact=not_supplied
finding_count=3
finding_1=V16-R1
finding_2=V16-R2
finding_3=V16-R3
```

Do not invent a review artifact, source authorization, validation pass,
recovery result, publication result, or concurrency execution.

## Required V16-R1 Recheck

Verify the publication authority and primitive:

- the retained v15 Q1/T1, Q2/T2, final Q3/T3, permit, and exact post-fsync temp
  readback remain unchanged;
- no-replace capability and frozen owner-tool identity are owner-independent
  route predicates in all three Q snapshots;
- unsupported or changed capability fails before permit with the complete
  retained zero-write semantics;
- source and target are relative to the same retained artifact-directory file
  descriptor;
- source is exactly the retained deterministic temp basename;
- target is exactly `creation_owner.json`;
- the operation has exact
  `renameat2(..., RENAME_NOREPLACE)` semantics;
- target absence at linearization atomically moves the exact source entry to
  the target and removes the source name;
- target presence at linearization returns `target_exists` and leaves both
  entries unchanged;
- any other operation failure leaves the exact source unchanged and performs
  no target creation, replacement, unlink, or modification;
- `published`, `target_exists`, and `io_failed` are the only operation
  outcomes;
- ordinary rename, overwrite, unlink-first rename, target precheck followed by
  rename, copy, hard-link/delete composition, shell `mv`, Git movement, and
  compatibility fallback are forbidden;
- the no-replace call occurs exactly once under the retained permit; and
- the permit is consumed on the first attempt and cannot retry or fall back.

Verify exact success ordering:

1. exact temp fsync and readback;
2. one no-replace publication;
3. artifact-directory fsync;
4. retained six-leaf owner-chain readback; and
5. only then the retained terminal/settlement/current-pointer transaction.

An implementation that uses an existence check plus replace-capable rename
fails V16-R1 even if its ordinary tests do not reproduce the race.

## Required V16-R2 Recheck

Verify exact conflict selection:

- final Q3 proved `creation_owner.json` absent;
- the retained permit and exact fsynced temp are valid;
- the no-replace operation was invoked exactly once;
- the operation returned canonical `target_exists`;
- those facts select if and only if
  `validation_creation_owner_recovery_io:owner_target_conflict`;
- the target is therefore classified as created after Q3;
- equal target bytes or a plausible owner chain do not permit adoption;
- the conflict is not mapped to `rename_failed`, preflight change, predicate
  mismatch, owner success, or publication success; and
- the result is a returned existing-materializer variant, not a new durable
  authority.

Verify every `OwnerTargetConflictResult v1` field:

- exact schema, kind, and public code literals;
- run ID, logical key, attempt, aggregate ID/revision, current-intent revision,
  pending event, lock, permit, and Q3 all equal the retained transaction;
- source basename is deterministic and target basename is exact;
- publication primitive and outcome literals are exact;
- complete non-null `temp_before_publish` and `temp_after_conflict`;
- one exhaustive `RacedOwnerReadback v1` member;
- one exact `OwnerTargetConflictSideEffects v1` object;
- RFC 8785/UTF-8/SHA256 body hash excludes only `body_sha256`; and
- no caller-supplied field, null identity, future-object identity, or
  self-reference exists.

Verify exact preservation:

- `temp_after_conflict` serializes byte-for-byte identically to
  `temp_before_publish`;
- no-replace failure leaves the deterministic temp name and exact bytes/node
  intact;
- the raced `creation_owner.json` entry remains intact;
- the recovery operation never adopts, deletes, overwrites, rewrites, cleans,
  quarantines, or replaces either entry;
- matching raced-owner bytes do not alter that rule;
- the failed transaction does not fsync the artifact directory;
- it writes no terminal event, settlement, successor aggregate, current
  pointer, durable conflict receipt, or pass artifact; and
- it returns without retrying the consumed permit.

Verify retry behavior:

- a later call reacquires the canonical lock;
- it begins fresh retained classification;
- the now-existing target enters the existing-owner route or its typed
  conflict;
- the consumed permit and missing-owner publication branch cannot resume; and
- retained temp cleanup requires separate canonical authority and is not
  inferred from this result.

## Required V16-R3 Recheck

Verify `RacedOwnerReadback v1` is exhaustive:

- common schema, state, path, node, content, and failure fields are always
  present;
- `complete_regular` requires a regular node, complete node identity, complete
  content SHA256/Git blob, matching no-follow lstat/open/fstat/readback, and
  null failure;
- `complete_non_regular` requires a listed non-regular kind and complete node
  identity while both content hashes and failure are null;
- `unstable_or_unreadable` requires one exact allowed failure, retains every
  observed node field, nulls unobserved fields, and nulls both content hashes;
- no free-form status, reason, error, omitted field, or non-exhaustive null
  fallback exists; and
- a later raced-actor mutation never grants write authority to the recovery
  operation.

Verify all conflict side-effect Booleans:

```text
no_replace_attempted=true
no_replace_succeeded=false
temp_unlinked=false
temp_replaced=false
temp_rewritten_after_readback=false
owner_unlinked=false
owner_overwritten=false
owner_adopted=false
cleanup_attempted=false
artifact_directory_fsync_attempted=false
terminal_event_written=false
settlement_written=false
successor_aggregate_written=false
current_pointer_updated=false
```

Verify the closed publication table includes distinct rows for:

- non-target-exists no-replace I/O failure;
- exact owner-target conflict;
- directory-fsync failure after successful publication;
- owner readback failure after directory fsync; and
- full success.

Verify the public concurrency negative:

- it uses the production materializer API and only a test-process scheduling
  barrier;
- Q3 observes owner absence;
- exact temp creation/fsync/readback completes;
- an external actor creates and fsyncs a distinct regular owner after Q3 and
  before the production no-replace call;
- no-replace returns target-exists;
- the exact conflict result is returned;
- both node/content identities and both path names remain unchanged;
- every forbidden side effect and state write is absent;
- equal raced-owner bytes remain a conflict without adoption;
- a fresh retry reclassifies owner-present state; and
- no test-only production selector, compatibility API, keyword route, or
  hand-written pass artifact is introduced.

## Required Retained-Contract Recheck

Return an explicit result for:

- v15 R1 exact reviewer-independence polarity, producer-assigned-reviewer
  equality, role validity, and all positive/inverse public oracles;
- v15 final-Q3-before-I/O ordering, permit identity/lifetime, complete
  pre-permit zero-write vector, and retained temp preservation;
- every unaffected v15 post-permit I/O row;
- v14 `CommandOutcome v3` exact route/argv/`argv_sha256` binding, variants,
  body hashing, equality/readback, and mismatch negative;
- v14 review/publication resolver precedence, simultaneous-condition failure
  derivation, projections, and public negatives;
- v12 C1 canonical locator, no public path overrides, deterministic artifact
  identity, three executable identity observations, stream EOF/completeness,
  repo/external module origin, and one materializer/L/current-attempt
  transaction;
- retained immutable intent/review DAG, automatic same-context independent
  review, explicit APPROVE, exact candidate/target publication CAS, external
  projection, validation provenance, and dirty-checkout isolation;
- D2/D3/F1/F2, member/group equality, topology/freeze, formatter statuses,
  dependency closure, and validation honesty;
- no compatibility/test-only API, new runner/ledger, self/fresh-review bypass,
  caller override, durable dependency to run-local reports, or self-reference;
  and
- every unaffected predecessor public oracle.

Only the final creation-owner publication concurrency algebra may replace v15
text.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V16_R1_no_replace_publication=pass|fail
V16_R2_owner_target_conflict=pass|fail
V16_R3_readback_side_effect_and_public_concurrency_oracle=pass|fail
v15_R1_and_pre_permit_zero_write=pass|fail
v14_CommandOutcome_v3=pass|fail
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
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v16.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v16.md
```

Expected design-author validation:

```text
tools/bin/agent-canon docs format <exact two paths>
tools/bin/agent-canon docs check <exact two paths>
git diff --check -- <exact two paths>
Git size/SHA256/blob readback
```

No Python, source tests, CI, dynamic graph, recovery execution, concurrency
execution, publication, `CommandOutcome` execution, OOP/SOLID execution,
review dispatch, or implementation formatter is authorized. All such
validation remains typed pending until this exact v16 target receives
independent APPROVE and later source implementation is authorized.
