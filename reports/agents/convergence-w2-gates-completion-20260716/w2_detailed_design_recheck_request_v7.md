# W2 Detailed-Design v7 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
```

This request asks an independent reviewer to evaluate only the exact v7 design
bytes identified below. It does not authorize source implementation, tests,
owner-document changes, hook changes, CI, dynamic graph execution, publication,
or automatic approval.

This request intentionally contains no identity for its own containing commit,
tree, Git blob, complete-file SHA256, or byte size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v7.md
target_size_bytes=134458
target_sha256=2a0df1aec3f2fbe8ec2d717ddf1ee8d8c29beadc27855f9631d34acc6b17d270
target_git_blob=76f04266d33bdb613a7606d5a731c9ad917f61a3
target_encoding=UTF-8
target_bom=absent
target_line_endings=LF
```

Before reviewing content, independently recompute the byte size, SHA256, and
Git blob. Any mismatch is:

`review_target_identity_mismatch`.

Do not review a reformatted, copied, regenerated, summarized, or
chat-transcribed version.

## Bound Predecessor

```text
predecessor_commit=772883acd2dbc6d0eab70fb789d0a73a4ed5a8b9
predecessor_tree=d6c413419782807fdd84e78692809627ed13f38a
predecessor_parent=1320951a179fbc63b7811535bb4c72813f31dedd
predecessor_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v6.md
predecessor_size_bytes=73249
predecessor_sha256=943a1f7f871ba839f29bfb547a237c3326a997d33e2c23fc1c4e45981d8675a5
predecessor_git_blob=2b1ed1ba4b3eb27d079fc2c36863157f22ad170f
```

The v7 design must be an append-only design successor of this predecessor.

## Bound REVISE Decision

```text
decision_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_decision_772883ac.md
decision_size_bytes=11435
decision_sha256=6130e6f467f9fa5dc59f252ca56b996916be64fbfbacac66236aadf6112fece0
decision_git_blob=71fbd97756ffca6a4a9cdc28538b6433d11683e1
decision=REVISE
finding_count=2
```

The two review blockers are V6-R1 total publication-route/reverse-edge closure
and V6-R2 deterministic orphan-temporary crash recovery.

The same-active-task user delta additionally requires V7-A1 automatic,
independent, repo-owned candidate review. It is part of this recheck and must
receive an explicit result.

## Required V6-R1 Recheck

Verify all of the following:

- total predecessor literal enumeration is exactly four executable/document
  raw-push surfaces plus one critical eval occurrence;
- root `README.md` is present in the Abstract Design Frame, Source Packet,
  Side-Effect Map, dependency pairs, implementation trace, acceptance, review,
  validation, and negative tests;
- the exact verified `github_publish.py --root vendor/agent-canon push` command
  replaces the raw route in root README, workflow index, derived workflow, and
  runtime update skill;
- active W2 delegates the exact frozen operation or fails typed before
  mutation; malformed active authority never falls back to non-W2;
- `AGENT-CANON-UPDATE-SHIM-2` retains its exact target/critical identity,
  requires canonical publication/integrator/refusal markers, and forbids the
  raw literal;
- `evaluate_skill_workflow_prompts.py` is the exact critical eval consumer;
- convention/drift checkers and tests cover the root route, critical eval, and
  every missing/kind-mismatched reverse edge;
- the direct caller set is exactly seven paths;
- every caller has the exact same-kind inverse relative path in
  `publication_integrator.py`;
- every newly introduced document/tool/eval/checker/test dependency pair has
  its exact same-kind inverse; and
- one expected-old-OID publication authority remains the only active-W2
  mutation route.

## Required V6-R2 Recheck

Verify all of the following:

- transaction body binds exact physical base plus target aggregate,
  current-intent, and formatter event IDs/hashes;
- the deterministic temp basename grammar and all hash ranges are exact;
- kernel lock ownership and the fsynced diagnostic owner record are distinct
  and complete;
- startup/retry classifies before `O_EXCL`;
- requested-transaction namespace enumeration and ordering are exact;
- safe-node checks, complete-byte equality, canonical parse, transaction/member
  equality, physical-base equality, target equality, and recovery fsync are all
  required before reuse;
- a crash between temp fsync and rename resumes through re-fsync, base reread,
  rename, directory fsync, and normal readback;
- exact already-committed orphan cleanup has narrow unlink authority and
  repeated readback;
- incomplete, corrupt, stale, conflicting, unsafe, non-matching, and live
  transaction temps are preserved with typed non-success;
- every crash boundary has one deterministic retry result;
- successful recovery proves aggregate/event/current-intent equality and no
  requested temp remains; and
- no stored success or hand-written artifact satisfies recovery.

## Required V7-A1 Automatic-Review Recheck

### Canonical activation and immutable identity

Verify:

- activation comes only from canonical `write_result_commit`,
  `source_freeze_commit`, and `pr_head_update` events;
- a coalesced write-result/source-freeze event dispatches once, while a PR-head
  update is a distinct external-state candidate;
- uncommitted worktree bytes, branch names, writer summaries, prompt text, and
  CI status cannot become candidate authority;
- lineage/request/context/candidate/frame ID byte streams, revisions, and
  attempts are exact and non-self-referential;
- candidate commit/tree/parents/base/diff/changed paths and PR head/base are
  mechanical readback;
- a later candidate monotonically supersedes the prior current pointer; a
  rejected repair never restores an older candidate.

### Repo-owned routing and minimal handoff

Verify:

- completion/review state is owned by `CODEX_WORKFLOW.md` and
  `COMMUNICATION_PROTOCOL.md`;
- routing/instance ownership is in `task_catalog.yaml`,
  `agents_config.json`, `CODEX_SUBAGENTS.md`, `.codex/config.toml`, and role
  TOMLs;
- the exact cross-owner implementation order is complete;
- T12 routes checkpoint review through
  `implementation_review/change_reviewer/diff_triage_reviewer` and publication
  review through `final_review/final_reviewer/ship_reviewer`;
- `review_dispatch.py` is only a replaceable adapter and accepts no
  candidate/writer/reviewer/decision identity override;
- dispatch uses canonical skill/tool-call routing and the private structural
  startup route, not keyword matching;
- the runtime handoff contains exactly `objective`, `owner_unit`,
  `fixed_source_packet`, and `acceptance_identity`;
- dispatch, revision, and re-review behavior is not embedded in a long subagent
  prompt;
- unexpected behavior is a typed missing/misplaced owner, structure, tool,
  checker, dependency, role-config, or routing-packet defect.

### Independence, compaction, and repair loop

Verify:

- reviewer identity differs from writer and parent;
- reviewer role/TOML is read-only and team write policy is artifact-only;
- parent remains monitor/integrator and never writes the review decision;
- writer and reviewer lineage IDs are durable;
- writer/reviewer resume locators contain exact runtime provider, parent/child
  runtime IDs, team-manifest role-instance ref, dispatch receipt, last frame,
  status, and observation time;
- after compaction, parent reads L/manifest/receipt, inspects nested agents, and
  resumes only the exact nested runtime ID;
- missing, ambiguous, foreign, or scope-mismatched nested-agent identity is a
  typed structure blocker, not a prompt workaround;
- REVISE findings include required intent-preservation and issue-routing
  fields, return to the same writer context, and create repaired candidate
  revision `n+1`;
- re-review preserves request ID, review context, reviewer assignment, reviewer
  lineage, clauses, and focus;
- a live reviewer resumes by exact runtime ID; a terminal reviewer can be
  replaced only through the owner-approved same-context resume event.

### Explicit approval and publication

Verify:

- reviewer decision algebra is exactly `APPROVE`, `REVISE`, `ESCALATE`;
- reviewer decision file does not hash its own complete file or containing Git
  identity;
- an external ledger binding supplies path/file SHA/blob and current
  candidate/frame equality;
- only the pair of explicit APPROVE decision body and valid external binding
  unlocks publication;
- local/main/remote CAS requires the current approved source candidate;
- remote candidate push may create a PR-head candidate, and the later PR merge
  CAS requires explicit approval of that exact current PR head;
- every new source commit or PR-head OID stales the prior receipt;
- no automatic approval, self-review, parent approval, CI-only approval,
  manual bypass, or old-candidate fallback exists;
- failed/stalled dispatch and all locator/owner/routing defects retain durable
  blocked evidence and keep publication locked.

### Local/GitHub equivalence

Verify:

- canonical ledger L is the sole review-state authority;
- local run artifacts and GitHub PR fields project the same lineage, request,
  context, frame, candidate, revision, reviewer assignment, state, decision,
  receipt, and publication lock;
- GitHub labels/checks/reviewDecision are projection-only;
- exact remote head/base readback is compared to L; and
- any projection mismatch fails typed and cannot unlock CAS.

## Required Non-Regression Recheck

Return an explicit result for:

- pre-review candidate attestation;
- independent review receipt bound to immutable B;
- post-APPROVE publication authority;
- immutable candidate ref/B and exact source tuple;
- immutable intent revisions and one current pointer;
- expected-old local/remote/PR CAS and post-readback;
- checked-out-target refusal;
- canonical ledger sole authority and pure projection;
- exact per-member source correspondence;
- exact cross-member equality;
- exact five formatter statuses and transition algebra;
- deferred-by-user and not-applicable authority evidence;
- D2;
- D3;
- F1;
- F2;
- exact freeze/topology/repair/escalation predicates;
- canonical tree-delta serialization;
- convention closure including `check_convention_consistency.py`;
- non-self-reference;
- no compatibility selector; and
- no test-only production API.

## Review Output Contract

Return findings first.

For every finding include:

- priority;
- exact artifact section/line evidence;
- violated clause;
- required design repair;
- intent preservation;
- issue route; and
- whether re-review is required.

Then return:

```text
decision=APPROVE|REVISE
V6_R1=pass|fail
V6_R2=pass|fail
V7_A1=pass|fail
retained_contracts=pass|fail
implementation_authorization=blocked|eligible_for_separate_source_stage
```

`APPROVE` is valid only when V6-R1, V6-R2, V7-A1, and every retained contract
pass against the exact target bytes.

## Expected Commit Scope

The design-only successor commit must have direct parent
`772883acd2dbc6d0eab70fb789d0a73a4ed5a8b9` and exactly these changed paths:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v7.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v7.md
```

Any source, test, owner-document, hook, config, workflow, skill, eval, or prior
artifact change is:

`design_only_scope_violation`.
