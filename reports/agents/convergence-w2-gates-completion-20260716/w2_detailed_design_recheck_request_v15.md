# W2 Detailed-Design v15 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V15-R1,V15-O1
owner_unit=retained review identity predicate and missing-owner recovery ordering
```

Review only the exact v15 bytes identified below. This request authorizes no
source implementation, tests, owner documents, hooks, Python, CI, dynamic
graph, review resolver execution, recovery execution, validation command,
review dispatch, publication, compatibility path, new runner, new ledger,
receipt, cleanup, or hand-written pass artifact.

Reviewer identity must differ from the design writer. Parent remains
monitor/integrator. REVISE returns findings to the retained same
writer/reviewer lineage and evaluates only the repaired successor.

This request contains no identity for its own bytes, Git blob, containing
commit, tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v15.md
target_size_bytes=38823
target_sha256=f80fc43e22584ebce29c2614e524708c82ef667d5b1fcfb613d756a9b93c2af4
target_git_blob=7d655afb274a76373f7e479f1660dab40794ac6d
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

## Bound v14 Predecessor

```text
predecessor_commit=d82efcf6872cbda9d61f73f702c4057555aa8c77
predecessor_tree=2f3bb76f953612a8ba30927d5336693c7b3a041e
predecessor_parent=15fbe1c6084c7f837ba87ff410ade5b8834c76be
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v14.md
predecessor_design_size_bytes=61013
predecessor_design_sha256=6ba4c6506f1cc2d99fed6bc4b9b69b93b7a602d544fab03e14d63b3c5737c9e2
predecessor_design_git_blob=e71dd1783a34f7c57166350aadbf3ec98aea40e1
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v14.md
predecessor_request_size_bytes=16518
predecessor_request_sha256=8aa2f49dc0683ee86253c86eb017d694e8e01ebf0bbc51a0233b2d6a29bf7536
predecessor_request_git_blob=f92b2292121dda58f78e6c7b224d8af2f2709c90
```

v15 is an append-only delta over this exact v14 packet. v14 normatively
incorporates v12 C1 and all retained v13-v8 contracts.

## Bound Review Input

```text
review_input_kind=explicit_user_v15_fixed_byte_closure
durable_decision_artifact=not_supplied
finding_count=2
finding_1=V15-R1
finding_2=V15-O1
```

Do not invent a review artifact, source authorization, validation pass, or
recovery result.

## Required V15-R1 Recheck

Verify canonical identity fields:

- `A` is the assigned reviewer runtime identity;
- `W` is the candidate writer runtime identity from the validation result;
- `P` is the validation producer runtime identity from the same result;
- `RR` is the required role in the current review frame;
- `AR` is the canonical assignment role for `A`;
- all identities are non-null, unique, current, and bound to the same
  candidate/revision/aggregate/intent/lineage/frame;
- missing context follows the retained v14 missing-context table; and
- malformed, duplicate, foreign, or cross-candidate identity is a structural
  error before `NI`.

Verify role validity:

- `RR` is exactly `change_reviewer` or `final_reviewer`;
- `AR` equals `RR`;
- canonical task/team routing selects `A` for the same role/frame;
- role configuration is the retained read-only independent-review config;
- role/instance/agent-type equals the canonical same-context assignment;
- `ROLE_INVALID` is the exact negation of those five requirements; and
- reviewer/parent collision, instance-key collision, missing resume lineage,
  or fresh-review substitution remains a separate structural predicate, never
  a fourth `NI` term.

Verify exact polarity:

- `SELF` is true exactly when `A` equals `W`;
- `PRODUCER_MISMATCH` is true exactly when `A` differs from `P`;
- `NI` is exactly `SELF OR PRODUCER_MISMATCH OR ROLE_INVALID`;
- no other condition contributes to `NI`;
- `NI` is false if and only if `A` differs from `W`, `A` equals `P`, and the
  role is valid;
- producer-assigned-reviewer equality is therefore mandatory;
- a different reviewer cannot inherit validation evidence;
- reviewer equality with producer is not a failure;
- reviewer difference from producer is a failure;
- reviewer difference from writer is not self-review;
- reviewer equality with writer is self-review even when writer, producer, and
  reviewer are the same identity;
- all eight S/M/R truth-table rows have the exact NI value;
- retained NI/DB/ST table, outcome precedence, null shape, generic NI failure
  code, ID framing, and body hashing are unchanged;
- retained typed causes are self-review, producer-not-assigned-reviewer, and
  role-invalid with the exact polarity; and
- readback recomputes all identity fields, role conjuncts, three terms, and
  `NI`.

Verify public polarity oracles:

- `A!=W`, `A=P`, valid role gives `NI=0`;
- `A=W`, `A=P`, valid role gives `NI=1`;
- `A!=W`, `A!=P`, valid role gives `NI=1`;
- `A!=W`, `A=P`, invalid role gives `NI=1`;
- treating `A=P` as failure is typed;
- treating `A!=P` as pass is typed;
- treating `A!=W` as self-review is typed;
- treating `A=W` as independent is typed;
- adding parent/fresh-lineage terms to NI is rejected; and
- ignoring any role-valid conjunct is rejected.

## Required V15-O1 Recheck

Verify retained preflight:

- v14 owner-independent predicates and exact five-leaf pre-owner root remain;
- stable existing lock, route/tool/frozen-source equality, completion absence,
  and non-self-reference remain;
- temp identity has the exact absent/present key set and null rules;
- present state is permitted only for one exact safe reusable candidate;
- temp identity hash is RFC 8785/SHA256 and is only an in-memory observation;
- scoped durable state is exhaustively listed; and
- zero-write excludes every recovery-owned content, namespace, mode, owner,
  explicit timestamp, ledger, transaction, or pointer mutation.

Verify exact read order:

- Q1/T1 is the first full read;
- Q2/T2 is a second full read under the same lock with no write/fsync between;
- creation-owner bytes, replacement content identity, safe-node policy, and
  deterministic basename are computed only in memory;
- no uncreated inode or device is predicted;
- Q3/T3 is a final complete base and temp reread;
- decoded predicates, Q1=Q2=Q3, and T1=T2=T3 are required;
- no new temp create, open-for-write, write, or fsync occurs before Q3;
- no existing exact temp fsync occurs before Q3;
- the ephemeral permit is issued only after Q3/T3 equality;
- permit digest fields/order are exact;
- permit is lock-bound, in-memory, one-branch, consumed on first I/O, and
  expires before retry; and
- permit derivation itself writes nothing.

Verify predicate-mismatch semantics:

- every retained predicate mismatch occurs before permit;
- Q/T/replacement/basename/lock/permit-derivation mismatch is a predicate
  mismatch;
- no predicate mismatch code is used after permit issuance;
- every mismatch has `permit_issued=false`;
- no temp is created, opened for write, written, fsynced, unlinked, or renamed;
- no directory fsync, owner creation, ledger append, settlement, or pointer
  update occurs;
- the recovery operation performs no temp or scoped durable mutation;
- the exact identity observed at mismatch detection is preserved through
  return;
- with no external actor, entry/detection/return identities are identical;
- an external transition between T1/T2/T3 is evidence only and the recovery
  performs no further transition;
- foreign/live/incomplete/corrupt/conflicting temp is preserved; and
- public negatives compare all scoped identities before and after.

Verify post-permit ordering:

- absent T3 permits exactly create, write, fsync, temp readback;
- present T3 permits only exact reusable-temp fsync and readback, never rewrite;
- successful branch then performs rename, directory fsync, and six-leaf owner
  readback;
- there is no post-temp predicate reread;
- any failure after permit is I/O or post-permit concurrency failure, not a
  predicate mismatch;
- terminal/settlement begins only after exact owner readback; and
- a retry always restarts lock-first with fresh Q1/Q2/Q3 and a new permit.

Verify the closed I/O failure table:

- exact namespace is `validation_creation_owner_recovery_io:`;
- all ten failure codes exist exactly once;
- create failure without node leaves temp and owner absent;
- O_EXCL conflict preserves the raced entry without adoption/deletion;
- write failure preserves partial/unknown temp;
- new-temp fsync failure preserves temp with unknown durability;
- reusable-temp fsync failure preserves exact prior temp;
- temp readback failure preserves temp and prevents rename;
- temp identity mismatch preserves mismatching temp;
- rename failure preserves exact temp and leaves owner absent;
- directory-fsync failure may leave exact owner with unknown durability and no
  temp;
- owner-readback failure leaves owner unaccepted and writes no terminal state;
- no post-permit failure unlinks, overwrites, quarantines, or adopts temp/owner;
- no post-permit failure writes terminal/settle/successor/pointer state;
- returned typed result records the exact observed side effect; and
- no I/O result is relabeled as preflight/predicate mismatch.

## Required Retained-Contract Recheck

Return an explicit result for:

- v14 CommandOutcome v3 exact route/argv/`argv_sha256` binding, variant
  semantics, body hashing, and negatives;
- v14 review/publication resolver tables, simultaneous conditions, failure
  arrays, projection IDs, readback, and no-projection behavior;
- v14 owner-independent predicates, successful owner creation, and six-leaf
  readback;
- v13 projection schemas, nullable seeds, validation result formula,
  creation-owner chain, VersionOutcome v2, and transition table;
- v12 C1 locator, no public path overrides, deterministic artifact identity,
  three observations, stream union, one materializer/L/current attempt, and
  begin/settle CAS;
- retained automatic review lineage, reviewer/parent separation, explicit
  APPROVE, publication authority, exact candidate/target, dirty-checkout
  protection, and CAS;
- D2/D3/F1/F2, per-member/group equality, topology/freeze, five formatter
  statuses, and reciprocal dependency closure;
- no compatibility/test-only API, new runner/ledger, self/fresh review bypass,
  keyword/prompt side path, caller override, durable dependency to run-local
  reports, or self-reference; and
- every unaffected predecessor public oracle.

Only V15-R1 and V15-O1 may replace v14 text.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V15_R1=pass|fail
V15_O1=pass|fail
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
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v15.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v15.md
```

Expected design-author validation:

```text
tools/bin/agent-canon docs format <exact two paths>
tools/bin/agent-canon docs check <exact two paths>
git diff --check -- <exact two paths>
Git size/SHA256/blob readback
```

Reviewer-predicate execution, recovery execution, post-permit I/O injection,
CommandOutcome execution, OOP/SOLID, public negative tests, review dispatch,
and publication remain typed pending. Source implementation remains blocked
until this exact v15 target receives independent APPROVE.
