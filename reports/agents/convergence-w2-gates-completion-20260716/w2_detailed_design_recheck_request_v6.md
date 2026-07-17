# W2 Detailed-Design v6 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
```

This request asks an independent reviewer to evaluate only the exact v6 design
bytes identified below. It does not authorize source implementation.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v6.md
target_size_bytes=73249
target_sha256=943a1f7f871ba839f29bfb547a237c3326a997d33e2c23fc1c4e45981d8675a5
target_git_blob=2b1ed1ba4b3eb27d079fc2c36863157f22ad170f
target_encoding=UTF-8
target_bom=absent
target_line_endings=LF
```

Before reviewing content, independently recompute the byte size, SHA256, and
Git blob. Any mismatch is:

`review_target_identity_mismatch`.

Do not review a reformatted, copied, regenerated, or chat-transcribed version.

## Bound Predecessor

```text
predecessor_commit=1320951a179fbc63b7811535bb4c72813f31dedd
predecessor_tree=6c2eeaaf2c64cfdae34b5dadf7f7af9ebe60e299
predecessor_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v5.md
predecessor_size_bytes=68970
predecessor_sha256=a618735a229261fce21f9d790a933c357626e73cc82b55d4541687c0de2a0561
predecessor_git_blob=a5e70b6f1bc4d6cc51b9479079c2f6842d483af4
```

The v6 design must be an append-only successor of this predecessor.

## Bound REVISE Decision

```text
decision_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_1320951a.md
decision_size_bytes=12546
decision_sha256=7f1110a9e0f273d3cdc36cb70f7462e6ec12192e2c48d6de7d1ff83a4d287e9d
decision_git_blob=3908c5f3972096e05502cd74a88f0dfd8f8f323a
decision=REVISE
finding_count=3
```

## Required Finding Recheck

### V5-R1 Publication/CAS route closure

Verify all of the following:

- one canonical publication authority owns local target refs, remotes, main,
  branch publication, and PR merge steps;
- `BRANCH_SCOPE.md`, main integration, AgentCanon PR workflow, PR queue,
  pr-processing canonical skill/shim/catalog, GitHub publish, direct helpers,
  hooks, automation, callers, headers, tests, and docs have exact future scope;
- every active-W2 ordinary merge/push/PR route delegates to the publication
  integrator or fails before mutation;
- a checked-out local target is refused with a typed failure;
- local CAS, exact remote lease, PR expected-base/head owner API, generated
  receipt, and post-update readback are exact;
- no alternate direct merge/push path remains.

### V5-R2 Pending/aggregate creation order

Verify all of the following:

- first intent row, pending event set, and aggregate snapshot are one atomic
  transaction;
- IDs and member hashes are constructible without self-reference;
- within-transaction references are legal while partial visibility is
  impossible;
- lock, expected head, same-directory temporary file, fsync, atomic replace,
  directory fsync, rollback, retry, and post-readback semantics are exact;
- bootstrap, repair retry, terminal settlement, deferral, and profile
  exclusion have a legal durable write order;
- partial append, future aggregate, missing pointer event, interrupted retry,
  and duplicate replay have typed public negatives.

### V5-R3 Formatter record union

Verify all of the following:

- exactly two ordered records retain schema, record ID, ordinal, check kind,
  and owner;
- all five statuses use one exhaustive fixed key set;
- `deferred_by_user` and `not_applicable` have exact event pointers/hashes,
  actor, authority, reason code, evidence refs, revision/current-intent
  equality, authority artifact path/body hash/file SHA/blob, and completion
  time;
- required, forbidden, null, and non-null fields are exact for every status;
- transition rules and pass equivalence are closed;
- no free-form omission or hand-written evidence bypass exists.

## Required Non-Regression Recheck

Return an explicit result for:

- pre-review attestation;
- independent review receipt;
- post-APPROVE publication derivation;
- immutable B and candidate ref;
- immutable intent revision list with one current pointer;
- expected-old-OID CAS and actual readback;
- convention-consistency closure;
- D2;
- D3;
- F1;
- F2;
- exact freeze/topology predicates;
- non-self-reference;
- no compatibility selector; and
- no test-only API.

## Reviewer Output Contract

The review artifact must:

1. lead with findings ordered by severity;
2. cite exact v6 line ranges and canonical owner/source paths;
3. classify every requested finding as `pass`, `partial`, or `fail`;
4. return exactly `APPROVE` or `REVISE`;
5. keep `implementation_authorization=blocked` unless the decision is
   `APPROVE`;
6. include external readback of the target path, byte size, SHA256, Git blob,
   containing commit, tree, and parent; and
7. omit the review artifact's own SHA256/blob/containing commit/tree from its
   bytes.

## Expected Design-Commit Path Scope

The design-only successor commit must change exactly:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v6.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v6.md
```

Any source, test, owner-document, hook, tool, catalog, template, or workflow
change in that commit is out of scope.

## Self-Identity Boundary

This request intentionally omits its own complete-file SHA256, Git blob,
containing commit, and containing tree. Those identities are external readback
evidence after the design-only commit exists.
