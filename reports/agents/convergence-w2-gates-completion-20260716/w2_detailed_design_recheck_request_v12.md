# W2 Detailed-Design v12 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V12-L1,V12-C1,V12-A1,V12-X1
owner_unit=existing materializer-backed validation route
```

Review only the exact v12 bytes identified below. This request authorizes no
source implementation, tests, owner documents, hooks, Python, CI, dynamic
graph, validation execution, review dispatch, publication, compatibility
route, or hand-written pass artifact.

Reviewer identity must differ from the design writer. Parent remains
monitor/integrator. REVISE returns findings to the retained same writer/reviewer
lineage and evaluates the repaired successor; it never selects an older
candidate or a fresh/self reviewer.

This request contains no identity for its own bytes, Git blob, containing
commit, tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v12.md
target_size_bytes=68762
target_sha256=900214147d7a1216729237296487fba1ad376d24894047cda71b6887aef1daab
target_git_blob=0b228053db2dc071781a459d94fb799fb79ef664
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

## Bound v11 Predecessor

```text
predecessor_commit=5a842b7f55da8237d81fa5a96c13f7f278245d1d
predecessor_tree=8f09dac76098bb4f1ed7e1f3b4c150fa3490635e
predecessor_parent=26b77aa9b1cebf731c603558a468245a0795e923
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v11.md
predecessor_design_size_bytes=72413
predecessor_design_sha256=fa98c755382ad5e401db6a878907cf04f086fdd9c719e264429d5a4db06fd406
predecessor_design_git_blob=6823aae2f1a4d3f19da150b4e39ed86d0ef48938
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v11.md
predecessor_request_size_bytes=11247
predecessor_request_sha256=71e9088d2544b5a75e72aa9ebc929fdee596bd47c1eea02b9bc6651920af43fa
predecessor_request_git_blob=2d77c2a10ff58913f3a6edaf7e268b2e87fff91c
```

v12 is an append-only delta over this exact v11 packet and all incorporated
v10/v9/v8 contracts.

## Bound Review Input

```text
review_input_kind=explicit_user_v12_closure
durable_decision_artifact=not_supplied
finding_count=4
finding_1=V12-L1
finding_2=V12-C1
finding_3=V12-A1
finding_4=V12-X1
```

Do not invent a review artifact, hash, blob, or decision.

## Required V12-L1 Recheck

Verify:

- exactly three pure generated projections exist in the order
  `validation_result -> review_eligibility -> publication_eligibility`;
- validation result owns only locator/materializer/route/current-attempt/
  artifact/executable/version/stream/process/output/clean-clone facts;
- validation result records producer evidence but does not evaluate reviewer
  role, review frame, decision, provider state, publication authority, target,
  or CAS;
- review eligibility first regenerates validation result;
- review eligibility adds only current candidate/frame/lineage/assignment,
  eligible reviewer role, producer-assigned-reviewer equality, writer
  inequality, same-context lineage, and current automatic-review structure;
- review eligibility does not inspect or require APPROVE/REVISE/ESCALATE,
  external provider state, publication authority, target, or CAS;
- publication eligibility first regenerates review eligibility;
- publication eligibility adds only explicit current local APPROVE, current
  external projection acknowledgement, publication authority,
  source/candidate/target equality, stale-state checks, and CAS preflight;
- publication eligibility performs no mutation and contains no post-CAS result;
- every projection schema, allowed outcome, predecessor ref, deterministic ID
  seed, body hash, sorted failure set, and null rule is exact;
- stored outcomes are projection-only;
- no resolver accepts a caller-supplied predecessor, path, outcome, or hash;
- publication and closeout cannot bypass the immediate predecessor projection;
  and
- stale/bypassed/malformed projections fail with the projection-specific typed
  error family.

## Required V12-C1 Recheck

Verify:

- `CanonicalRunLocator v1` is a pure snapshot, not a new ledger;
- fixed `<repo>/reports/agents/.active_run` and `.active_run.sha256` are the
  only locator sources;
- no environment, CLI, current subdirectory, submodule pointer, report root,
  run ID, or caller path can replace them;
- pointer and baseline are stable no-follow regular-file reads;
- pointer bytes are strict UTF-8, exactly one absolute normalized path plus LF;
- pointer value is one direct non-symlink child of the canonical report root;
- baseline is exactly 64 lowercase hex plus LF and matches pointer-byte SHA256;
- run ID, report directory, task-authority leaf, work-log leaf, and ledger run
  ID correspond exactly;
- locator schema, ID seed, body hash, and reread points before begin, settle,
  review eligibility, and publication eligibility are exact;
- public production APIs have exactly the four v12 signatures;
- `workspace` is repository context, not report-path authority;
- no public API or CLI accepts report directory/root, run ID, route ID/list,
  artifact ID/root/path, route-record path, manifest/raw path,
  projection/receipt path, or expected outcome;
- active required route set is derived and exactly `python.ruff.full`;
- tests use the real canonical temporary-repository layout without a test-only
  override; and
- moved, malformed, foreign, stale, or overridden locator state fails before
  artifact creation, review, or publication.

## Required V12-A1 Recheck

Verify:

- artifact seed contains exactly logical-key SHA256, 16-hex attempt ordinal,
  pending-event ID byte length, exact pending-event ID bytes, and pending-event
  canonical SHA256;
- seed byte range and NUL delimiters are exact;
- artifact ID, digest, run-relative root, and repo-relative root are
  deterministic;
- absolute root derives only from canonical run locator plus run-relative root;
- authoritative leaf set is exactly the five sorted v12 leaves;
- no extra leaf, nested directory, symlink, mutable latest, summary, or receipt
  is authoritative;
- generic manifest records exact locator/logical-key/attempt/pending-event/
  artifact identities without its own complete-file identity or future event/
  transaction/pointer/eligibility;
- attempt lock and temp names derive from the same digest;
- retry inspects locator, L, pending event, lock, root, and leaves in exact
  order;
- a complete byte-equal root is reused without command re-execution;
- an empty owner-matching pre-spawn root may resume;
- partial stream capture is retained as failed evidence and requires a new
  attempt;
- only proven stale owner-matching temps may be removed with directory fsync;
- live, foreign, corrupt, extra-leaf, symlink, or mismatched roots are never
  deleted/overwritten;
- settle replay succeeds only after artifact/event/pointer/transaction
  equality; and
- one logical-key/attempt/pending event can never allocate a second artifact
  identity or path.

## Required V12-X1 Recheck

Verify:

- route v2 removes `command.executable_chain` and adds one exact
  execution-identity contract;
- route v1 is rejected without a compatibility selector;
- expected launcher/module-origin pair is resolved before begin but is not a
  semantic observation;
- manifest contains exactly three observation records;
- observation ordinals/phases are exactly before version, after version
  capture before validation, and after validation capture;
- all three exist even when version spawn fails or validation is not run;
- observation schema, ID seed, body hash, timestamp ordering, pair hash, and
  complete identity objects are exact;
- launcher retains the v11 repo-path-blob versus external-file-bytes union;
- module origin is exactly `repo_module_origin` or
  `external_module_origin`;
- both module variants use one key-compatible object with exact null, Git,
  fstat, mode, size, SHA, and path rules;
- repo origin equals the candidate tree and clean-clone bytes;
- external origin is a stable final regular file under the exact environment;
- namespace, built-in, frozen, zip, pseudo, missing, or caller-supplied origin
  fails;
- launcher/module kind and bytes are equal across all three observations;
- version links observations 1 and 2;
- validation links observations 2 and 3;
- every version and validation command has stdout then stderr stream records;
- stream state is exactly EOF-complete, capture-failed, or not-created with the
  complete boolean/error/artifact combination;
- complete cannot exist without EOF;
- capture limit/truncation cannot pass;
- unsupported version uses not-created streams only under exact owner policy;
- validation-not-run after version failure is explicit with not-created
  streams and exact failure reference;
- pass requires exited 0 and every executed stream EOF-complete;
- output framing, normalization, environment, candidate, and clean-clone
  strength remains at least v11; and
- every missing/extra/order/link/kind/null/EOF/path/hash/identity/readback
  mismatch has a typed public negative.

## Required v11/v10/v9/v8 Non-Regression Recheck

Return an explicit result for:

- v11 single materializer/L, registered route, current attempt, begin/settle
  CAS, deterministic readback, no receipt ledger, and validation honesty;
- v10 local event sole authority and typed external projection;
- v9 one-way immutable reviewer DAG;
- v8 source packet correction, artifact identity/import, reviewer lineage,
  automatic review, and candidate-OID publication;
- exact dirty-checkout preservation and expected-old-OID CAS;
- publication route inventory and no alternate direct merge/push route;
- immutable intent revision list and one current pointer;
- per-member source-event correspondence and exact group equality;
- D2 branch reason and D3 owner/state/API/dependency/responsibility/outcome/
  evidence equality;
- exact freeze/topology predicates;
- five formatter statuses and pending/deferred/not-applicable honesty;
- no self/fresh review bypass, keyword/prompt route, or CI-only inference;
- no compatibility/test-only API;
- no durable dependency to run-local reports;
- no self-referential artifact; and
- every retained public negative oracle.

Only V12-L1, V12-C1, V12-A1, and V12-X1 may replace v11 text.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V12_L1=pass|fail
V12_C1=pass|fail
V12_A1=pass|fail
V12_X1=pass|fail
v11_v10_v9_v8_retained_contracts=pass|fail
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
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v12.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v12.md
```

Expected design-author validation:

```text
tools/bin/agent-canon docs format <exact two paths>
tools/bin/agent-canon docs check <exact two paths>
git diff --check -- <exact two paths>
Git size/SHA256/blob readback
```

Canonical locator execution, deterministic replay, three identity
observations, stream EOF execution, linear projection execution, OOP/SOLID,
public negative tests, and publication integration remain typed pending.
Source implementation remains blocked until this exact v12 target receives
independent APPROVE.
