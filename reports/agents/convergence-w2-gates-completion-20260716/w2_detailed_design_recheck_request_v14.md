# W2 Detailed-Design v14 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V14-R1,V14-O1,V14-C1
owner_unit=existing projection resolver and materializer artifact contract
```

Review only the exact v14 bytes identified below. This request authorizes no
source implementation, tests, owner documents, hooks, Python, CI, dynamic
graph, resolver execution, missing-owner recovery, validation command, review
dispatch, publication, compatibility route, new runner, new ledger, receipt,
or hand-written pass artifact.

Reviewer identity must differ from the design writer. Parent remains
monitor/integrator. REVISE returns findings to the retained same
writer/reviewer lineage and evaluates the repaired successor, never an older
candidate or a fresh/self reviewer.

This request contains no identity for its own bytes, Git blob, containing
commit, tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v14.md
target_size_bytes=61013
target_sha256=6ba4c6506f1cc2d99fed6bc4b9b69b93b7a602d544fab03e14d63b3c5737c9e2
target_git_blob=e71dd1783a34f7c57166350aadbf3ec98aea40e1
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

## Bound v13 Predecessor

```text
predecessor_commit=15fbe1c6084c7f837ba87ff410ade5b8834c76be
predecessor_tree=2d324f2cfebc7983df0c8bbf07ca44594eb383a0
predecessor_parent=47a4bb0516d7d320511c4671970a8b23cef0211f
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v13.md
predecessor_design_size_bytes=58192
predecessor_design_sha256=3ddb21cff86dc947bebedf8e5b35bd9f799ebd6fa4d100e0637a3299fc2cb9b8
predecessor_design_git_blob=ab14becc1d546f661d8c1b4f2e95ac9aef493f39
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v13.md
predecessor_request_size_bytes=11897
predecessor_request_sha256=e6d637271e2dfeef60e793b0b4ce8a300de85c5e538aed6566f578f1f5ad0439
predecessor_request_git_blob=8b4350038f02f2d2f8a6e2f980455659eba77816
```

v14 is an append-only delta over this exact v13 packet. v13 normatively
incorporates v12 C1 and all retained v12-v8 contracts.

## Bound Review Input

```text
review_input_kind=explicit_user_v14_deterministic_closure
durable_decision_artifact=not_supplied
finding_count=3
finding_1=V14-R1
finding_2=V14-O1
finding_3=V14-C1
```

Do not invent a review artifact, hash, blob, decision, source authorization,
validation pass, or recovery result.

## Required V14-R1 Recheck

Verify the common resolver contract:

- public resolver APIs accept only the retained workspace-root input and
  derive all predicates from canonical evidence;
- caller outcome, failure list, predicate, precedence, path, route, approval,
  authority, source, candidate, and target inputs are forbidden;
- predicate state is exactly true, false, or internally derived
  `not_evaluated`;
- malformed, contradictory, foreign, duplicate, stale-selected, unreadable,
  schema-invalid, owner-invalid, or hash-invalid evidence returns typed error
  and no projection;
- every accepted stage produces exactly one outcome, v13 null shape, exact
  ordered failure array, v13 projection ID, and body hash;
- conflicts produce no projection object or ID;
- failure arrays use only the fixed filter, in fixed order, without omitted,
  added, duplicated, reordered, or free-form entries;
- projection readback regenerates predicates, row, outcome, nulls, failure
  array, ID, and body byte-for-byte; and
- immediate-subject absence remains v13 no-projection, while negative or
  malformed evidence is not absence.

Verify review resolution:

- non-pass validation stops with exact `validation_not_pass`, all context
  fields null, one exact failure code, and later facts not evaluated;
- review context presence uses exact `L/F/R` meanings;
- all eight presence combinations are listed;
- `000`, `100`, and `110` are the only legal missing-context combinations;
- all other incomplete dependency combinations fail
  `review_eligibility:context_dependency_conflict`;
- legal missing-context rows emit all three context fields null;
- missing-context failure arrays contain the generic code and exactly the
  absent lineage/frame/reviewer codes in fixed order;
- complete context derives `NI`, `DB`, and `ST` only from canonical evidence;
- precedence is exactly stale, then reviewer-not-independent, then
  dispatch-blocked, then eligible;
- precedence chooses the outcome without discarding simultaneous failures;
- all eight `NI/DB/ST` rows have exact outcomes and exact ordered arrays;
- every accepted row changes a referenced identity or failure array before ID
  hashing;
- an unmapped row is typed and has no ID; and
- public tests include every legal row, every context conflict, omitted
  simultaneous code, reordered code, wrong precedence result, and readback
  change.

Verify publication resolution:

- absent review subject returns only v13 no-projection;
- malformed review subject returns typed error and no projection;
- noneligible review with no current-bound downstream evidence returns exact
  `review_not_eligible`;
- current-bound approval, authority, or target evidence under a noneligible
  review is a typed conflict, not ignored;
- foreign/older downstream binding cannot become current evidence;
- `A/U/T` have the exact approval, authority, and complete tuple meanings;
- partial source/candidate/target is always typed conflict;
- all eight `A/U/T` rows have the exact normal/conflict result;
- authority without approval, tuple without authority, and tuple missing after
  authority have the exact typed result;
- `approval_missing` and `authority_missing` have exact one-code arrays and
  later predicates not evaluated;
- complete chain derives `NR` and `ST` from retained target/CAS/staleness
  predicates;
- precedence is exactly stale, then target-not-ready, then eligible;
- all four `NR/ST` rows have exact outcomes and complete ordered arrays;
- both simultaneous failure facts remain in the `NR=1,ST=1` array; and
- public tests cover all presence rows, all simultaneous rows, partial tuple,
  downstream-under-noneligible, code mutation, ID mutation, and readback
  mutation.

## Required V14-O1 Recheck

Verify scope and ownership:

- missing-owner recovery remains inside the existing `work_log.py`
  materializer and existing begin/settle/current-attempt transaction;
- it applies only to the deterministic root with missing
  `creation_owner.json`, pending attempt, and no completed terminal/settlement;
- no new recovery ledger, runner, receipt, path override, or public selector
  exists; and
- stable lock acquisition uses an existing lock file without create or
  truncate.

Verify the zero-write boundary:

- phase 1 is exactly inspect-only;
- before phase 2, permitted operations are read-only open, `lstat`, read,
  enumerate, hash, existing-lock acquisition, and in-memory computation;
- before phase 2 there is no create, truncate, byte write, chmod/chown,
  intentional timestamp change, temp create/delete/unlink/rename/quarantine,
  ledger append, settlement, pointer update, or pass artifact;
- every preflight mismatch returns before the first durable write; and
- public failures prove root, lock, temp namespace, L, aggregate, pending
  event, and pointers are byte-for-byte unchanged.

Verify exact pre-owner structure:

- canonical leaf tuple is exactly result manifest, validation stderr/stdout,
  and version stderr/stdout in the documented UTF-8 order;
- all five are exact regular single-link safe nodes;
- creation owner is absent;
- no additional authoritative leaf, nested directory, symlink, alias,
  summary, receipt, latest pointer, compatibility file, or caller path exists;
- manifest leaf list and order equal the tuple;
- every leaf size, SHA256, Git blob, stream state, EOF/completeness, and
  complete read passes;
- retained temp namespace is separate and contains zero or one exact safe
  transaction candidate; and
- foreign, live, multiple, unexpected, unsafe, incomplete, corrupt, or stale
  temp state is preserved and typed.

Verify every owner-independent predicate:

- locator, logical key, attempt, aggregate/revision/intent, begin transaction,
  pending event, and current pointer;
- deterministic artifact seed/ID/root and stable lock path;
- existing lock ID/body/path/file identity;
- exact root, manifest, raw bytes, and no future reference;
- uniquely selected registered route v2;
- route candidate/logical-key/attempt/pending/cwd/environment/version policy/
  command argv/argv hash equality;
- exact `work_log.py` owner path/commit/tree/blob equality across lock,
  manifest, route definition owner, and frozen source;
- candidate/source/profile/catalog/wrapper/owner-tool frozen-source tuple;
- absence of terminal event, settlement, successor aggregate, or completed
  current pointer; and
- one-way non-self-reference.

Verify Q1/Q2 and mutation:

- the in-memory preflight fingerprint uses every documented term in exact
  order and is never persisted as authority;
- lstat and five-leaf vectors contain the exact listed fields;
- Q1 and Q2 are computed under the same lock with zero writes between them;
- decoded predicate equality and fingerprint equality are both required;
- mismatch is `preflight_changed` with zero writes;
- only after equality may the retained O_EXCL create/reuse/fsync/rename route
  begin;
- creation-owner `created_at_utc` is the pending event's canonical timestamp,
  never retry wall-clock time;
- exact base predicates are reread immediately before rename;
- any changed base preserves the temp and prevents owner/ledger/pointer writes;
- success fsyncs and rereads the resulting six-leaf root and complete owner
  chain before terminal/settle; and
- every listed mismatch has a public zero-write negative.

## Required V14-C1 Recheck

Verify schema closure:

- CommandOutcome v3 replaces v2 and v2 is rejected without compatibility
  selection;
- executed and not-run variants have exactly the same documented keys;
- route ref, argv, and `argv_sha256` are present and non-null in both;
- no additional runner, ledger, receipt, compatibility reader, or test-only
  API exists.

Verify route and argv equality:

- route is derived from the canonical current attempt and active profile, not
  from the caller;
- command outcome route ref equals manifest, pending/current-attempt selection,
  and canonical registered route v2 ID/body hash;
- argv equals route command argv element-for-element, count-for-count, and
  UTF-8-byte-for-byte;
- each argv element is non-empty UTF-8 without NUL;
- `argv_sha256` equals the route hash and SHA256 over RFC 8785 canonical argv
  array bytes;
- shell strings, token splitting, interpolation, globbing, quick-mode
  substitution, root omission, reordering, and caller argv are forbidden.

Verify variant semantics:

- executed requires captured or unsupported version outcome;
- executed uses the existing materializer launch boundary exactly once with
  the exact registered argv;
- executed has non-null exited/signaled/spawn-failed termination and null
  version-failure ref;
- spawn failure remains executed;
- not-run requires failed version outcome;
- not-run retains the intended registered route, argv, and hash while making
  no execution claim;
- not-run has no process launch, null termination, exact non-null version
  failure ref, two not-created streams, and `complete=false`;
- any not-run launch/termination/created stream is typed;
- observations remain version 1-to-2 and command 2-to-3;
- the retained three legal and three forbidden version-command rows are exact.

Verify readback and hashing:

- checker rereads canonical route v2, current attempt, manifest, candidate,
  owner source, and frozen source;
- route ref and argv/hash equality recompute before accepting validation
  result;
- executed launch argv readback equals route argv;
- not-run has no launch readback claim;
- stream/termination/failure-ref/complete/combined-output predicates remain
  exact;
- `command_outcome_body_sha256` covers the RFC 8785 complete v3 object with
  only its own field omitted, including route ref, argv, and argv hash;
- route/current attempt is reread immediately before acceptance; and
- every missing, foreign, altered, reordered, substituted, hash, launch,
  not-run, readback, and body mutation has the exact typed public negative.

## Required v12 C1 And Retained-Contract Recheck

Return an explicit result for:

- fixed canonical `.active_run` and baseline locator;
- exact locator schema/readback and workspace-only public APIs;
- zero public report root/directory, run ID, route, artifact, manifest, raw
  stream, projection, or receipt path override;
- deterministic artifact seed/root/lock path and materializer ownership;
- exactly three executable/module identity observations;
- repo/external module origin union;
- stream EOF-complete/capture-failed/not-created union;
- one materializer, one L, one current attempt, begin/settle CAS, and retained
  crash recovery;
- v13 ProjectionResolution/NoProjection and all three projection v2 schemas;
- canonical nullable seeds and exact validation result ID formula;
- creation-owner chain, stable lock, six-leaf complete root, replay equality,
  external terminal binding, and non-self-reference;
- VersionOutcome v2, version failure ref, and exact transition table;
- linear validation-result to review-eligibility to publication-eligibility
  responsibility direction;
- v11/v12 registered route/cwd/environment/executable/frozen-source strength;
- v10 local event sole authority and external projection;
- v9 one-way review DAG;
- v8 automatic review, same-context lineage, artifact binding, candidate-OID
  publication, dirty-checkout protection, and expected-old-OID CAS;
- publication route inventory and no alternate direct merge/push route;
- immutable intent revision list and one current pointer;
- per-member source-event correspondence and group equality;
- D2/D3/F1/F2, freeze/topology, five formatter statuses, and reciprocal
  convention closure;
- no self/fresh review bypass, prompt/keyword side path, or CI-only inference;
- no compatibility/test-only API, durable dependency to run-local reports, or
  self-referential artifact; and
- every retained public negative oracle.

Only V14-R1, V14-O1, and V14-C1 may replace v13 text.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V14_R1=pass|fail
V14_O1=pass|fail
V14_C1=pass|fail
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
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v14.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v14.md
```

Expected design-author validation:

```text
tools/bin/agent-canon docs format <exact two paths>
tools/bin/agent-canon docs check <exact two paths>
git diff --check -- <exact two paths>
Git size/SHA256/blob readback
```

Resolver execution, missing-owner recovery, command execution, OOP/SOLID,
public negative tests, review dispatch, and publication integration remain
typed pending. Source implementation remains blocked until this exact v14
target receives independent APPROVE.
