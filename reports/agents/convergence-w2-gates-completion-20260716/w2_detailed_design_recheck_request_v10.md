# W2 Detailed-Design v10 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V10-L1,V10-X1,V10-V1
```

This request asks an independent reviewer to evaluate only the exact v10 design
bytes identified below. It authorizes no source implementation, tests, owner
documents, hooks, Python, CI, dynamic graph, publication, compatibility route,
or hand-written pass artifact.

This request contains no identity for its own bytes, blob, containing commit,
tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v10.md
target_size_bytes=70791
target_sha256=4ee788cce9d0b100b607e3d3f9637feae06f5ab3cd5e80dda5fe536872b23693
target_git_blob=23a3431fcacdb34504c01c07431754d2c94df9e1
target_encoding=UTF-8
target_bom=absent
target_line_endings=LF
target_identity_authority=canonical_tool_readback
```

Independently recompute size, SHA256, and Git blob before content review. Any
mismatch is:

`review_target_identity_mismatch`.

Do not review a reformatted, summarized, copied, regenerated, or
chat-transcribed target.

## Bound v9 Predecessor

```text
predecessor_commit=f46e5214e8554dbb4d5a03e745cdf8ecf41d6f20
predecessor_tree=ab308243c2d00225aa6f9141c5b68371ed322bcd
predecessor_parent=0c5bfb817f1db7c0dee2026f9938ebe7139bb4eb
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v9.md
predecessor_design_size_bytes=46579
predecessor_design_sha256=46c85c546147d830ac31a556467d07c5676acb858a4175cb1a1284ebc0dcb793
predecessor_design_git_blob=16b5670f5b99b2beba5ab112b8c0efcdba6f2e63
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v9.md
predecessor_request_size_bytes=6191
predecessor_request_sha256=a7a975788c0fd9bfc085626f2ef7aef1184d7810c9f1899b01ea507b6a506085
predecessor_request_git_blob=9712c428de9f0454704120f8347130f2b19cc09e
```

v10 is an append-only delta over this exact v9 packet and its incorporated v8
packet.

## Bound Review Input

```text
review_input_kind=explicit_user_simplification_and_observed_validation_defect
durable_decision_artifact=not_supplied
finding_count=3
finding_1=V10-L1
finding_2=V10-X1
finding_3=V10-V1
```

No review artifact path/hash/blob may be invented.

## Required V10-L1 Recheck

Verify:

- the approved five-stage DAG remains exactly intent, frame, event, external
  acknowledgement, current pointer;
- `TerminalResumeEvent v3` replaces v2 without a compatibility selector;
- every event artifact-identity, local receipt identity, receipt path/hash/blob,
  and provider-response-byte field is forbidden at every depth;
- event intent/frame/candidate/assignment/context fields match durable
  predecessors;
- event candidate commit/tree equals canonical candidate readback;
- Codex provider object/parent equals reviewer/parent runtime identity;
- resume mode reuses the exact assigned reviewer runtime and replacement mode
  preserves assignment/lineage/context with an owner-selected distinct runtime;
- event ID seed and RFC 8785 body hash are exact and contain no future object;
- `(resume_event_id, resume_event_body_sha256)` is the sole local transition
  authority;
- no complete-file SHA, Git blob, receipt identity, raw provider digest, or
  prose is required; and
- v9 write/fsync/readback, crash recovery, reviewer independence, and
  non-self-reference remain exact.

## Required V10-X1 Recheck

Verify:

- stage four uses exactly
  `agent-canon.external-projection-acknowledgement.v1`;
- acknowledgement references exactly one existing local ledger event ID/body
  hash and no local artifact identity;
- projection kind/local event schema/local event kind/provider kind/object kind
  combinations are a closed four-row union;
- Codex, GitHub PR-head, GitHub review, and GitHub ref-update null rules are
  exhaustive;
- candidate ID/revision/body/commit/tree equality is exact for every variant;
- Codex object/parent/operation/status maps to event v3 and status progression
  is monotone under the exact table;
- GitHub repository/object/head/status maps to the current local
  trigger/decision/publication event;
- GitHub status cannot create local APPROVE, REVISE, ESCALATE, or publication
  authority;
- provider readback SHA hashes only the normalized typed provider projection;
- raw HTTP/RPC/terminal/receipt bytes are not hashed or compared to local
  bytes for gate authority;
- acknowledgement ID seed/body hash are exact and non-self-referential;
- no public API accepts caller event/provider/candidate/head/status overrides;
- provider readback repeats immediately before pointer/publication use;
- later external movement makes projection stale without rewriting local event
  or local state; and
- every mismatch, null error, stale version, replay, readback change, and
  authority inversion has a typed public negative.

## Required V10-V1 Recheck

Verify:

- executed validation evidence uses exactly
  `agent-canon.validation-execution-receipt.v1`;
- receipt records exact candidate ID/body/commit/tree/diff and monotone
  validation attempt;
- exact process argv is an ordered UTF-8 array and its canonical hash is
  defined;
- exact absolute cwd, repository identity, and repo-relative cwd are recorded;
- the registered environment profile source/version/hash, runtime kind,
  container null rule, sorted selected environment value hashes, and
  environment fingerprint are complete;
- tool ID, exact version argv/text/output hash, executable path, and executable
  identity are complete;
- process termination kind, exit code, signal, spawn error, stdout/stderr
  sizes/hashes, combined-output framing/hash, and completeness are exact;
- manager/reviewer frame null rules, termination unions, tool-version success
  and failure unions, and output-completeness rules are exhaustive;
- validation executes in a clean true clone at the exact candidate OID/tree
  and leaves HEAD/tree/status unchanged;
- dirty current checkout state is never included, reverted, stashed, restored,
  or cleaned;
- owner tool commit/tree/blob and producer role/runtime are recorded;
- gate-eligible producer differs from writer and approval/publication requires
  a change/final reviewer producer;
- stored `status` is projection-only and pass is recomputed from all receipt
  predicates;
- `pending`, `deferred_by_user`, and `not_applicable` remain the approved
  canonical evidence variants and cannot impersonate pass;
- writer prose, copied Ruff output, emoji lines, PR checkboxes, report tables,
  and hand-written artifacts cannot satisfy automatic review approval or
  publication;
- required check set comes from the exact active runtime profile;
- quick-mode skip cannot satisfy `python.ruff.full`;
- a new candidate invalidates old receipts;
- a later independent fail becomes current and invalidates an earlier pass and
  approval; and
- missing/foreign/stale/fail receipts keep publication locked with typed
  evidence.

## Required v9/v8 Non-Regression Recheck

Return an explicit result for:

- V9-R1 with only event-v3/acknowledgement substitutions;
- V9-R2 generic artifact identity v2 source-kind rules;
- V8-I1;
- V8-I2 local-byte identity/import/readback;
- V8-D1;
- V8-L1;
- V8-P1;
- V6-R1;
- V6-R2;
- V7-A1;
- all preserved v6 contracts;
- five formatter statuses and transition honesty;
- D2/D3/F1/F2;
- publication CAS and dirty-checkout exclusion;
- automatic review and same-writer/same-reviewer repair lineage;
- no compatibility/test-only API; and
- every retained public negative plan.

The only legal substitutions are V10-L1, V10-X1, and V10-V1.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V10_L1=pass|fail
V10_X1=pass|fail
V10_V1=pass|fail
v9_v8_retained_contracts=pass|fail
implementation_authorization=blocked|eligible_for_separate_source_stage
```

`APPROVE` is valid only when all three v10 clauses and every retained v9/v8
contract pass against the exact target bytes.

## Expected Commit Scope

The design-only successor commit must have direct parent
`f46e5214e8554dbb4d5a03e745cdf8ecf41d6f20` and exactly:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v10.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v10.md
```

Any source, test, owner-document, hook, config, workflow, skill, eval, prior
artifact, or unrelated path change is:

`design_only_scope_violation`.
