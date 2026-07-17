# W2 Detailed-Design v9 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V9-R1,V9-R2
```

This request asks an independent reviewer to evaluate only the exact v9 design
bytes identified below. It authorizes no source implementation, tests, owner
documents, hooks, Python, CI, dynamic graph, publication, or compatibility
route.

This request contains no identity for its own bytes, blob, containing commit,
tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v9.md
target_size_bytes=46579
target_sha256=46c85c546147d830ac31a556467d07c5676acb858a4175cb1a1284ebc0dcb793
target_git_blob=16b5670f5b99b2beba5ab112b8c0efcdba6f2e63
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

## Bound v8 Predecessor

```text
predecessor_commit=0c5bfb817f1db7c0dee2026f9938ebe7139bb4eb
predecessor_tree=0992f17f6f1b8981fd3e47b164020023924a7b3e
predecessor_parent=3fab576c1bf1a4621ae69778859b441fbaf7bda9
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v8.md
predecessor_design_size_bytes=205113
predecessor_design_sha256=7c310a2befb32290781a42ab9b2043b405a18da5cecf6598784c10096519659a
predecessor_design_git_blob=f1d612ae990ad9b810cef475992a6e6873c68118
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v8.md
predecessor_request_size_bytes=9714
predecessor_request_sha256=0961bc7fc48b5fa4e4d14ff9f9c7f07c6421aced9db811b6665adafd8339c608
predecessor_request_git_blob=b4eb8f7b4388e2df7208f76fcb8ca8a7a7459621
```

v9 is an append-only delta over this exact v8 packet.

## Bound Review Input

```text
review_input_kind=explicit_user_simplification_packet
durable_decision_artifact=not_supplied
finding_count=2
finding_1=V9-R1
finding_2=V9-R2
```

No review artifact path/hash/blob may be invented.

## Required V9-R1 Recheck

Verify:

- the only state-object order is intent, frame, event, external binding,
  current pointer;
- each node references/hashes only already durable predecessors;
- intent contains no frame/event/binding/pointer identity;
- frame contains only intent identity among new DAG nodes;
- event contains intent/frame/local-receipt identity but no binding/pointer;
- external binding contains intent/frame/event/provider identity but no
  pointer;
- no ID seed contains future bytes, path, provider result, or hash;
- `TerminalResumeIntent v1`, frame v3, and `TerminalResumeEvent v2` schemas,
  enums, IDs, hashes, and equality predicates are exact;
- the four-field reviewer handoff is unchanged;
- intent, frame, event, and binding are separately written, fsynced, and read
  back in order;
- review state stays `dispatch_pending` until binding readback;
- one later CAS advances all chain pointers, reviewer locator, and state to
  `dispatched`;
- crash recovery resumes from the last durable node and never blindly
  redispatches or selects a fresh reviewer;
- unknown provider dispatch state is typed blocked; and
- v8 same-context, reviewer independence, terminal algebra, and no
  prompt/keyword/CI/self-review bypass remain exact.

## Required V9-R2 Recheck

Verify:

- artifact identity schema v2 permits only `git_commit_path` and
  `filesystem_immutable`;
- `external_immutable_receipt` is invalid;
- source-binding null rules are exhaustive;
- external receipt bytes first receive a local artifact identity v2 record;
- one `ExternalArtifactBindingEvent v1` owns provider/object/receipt identity;
- reviewer-resume and GitHub publication variants use one fixed key set;
- all variant null/non-null rules are exact;
- provider/object/receipt IDs, versions, OIDs, parent IDs, local identity
  records, and readback hash are complete;
- the external binding ID seed and RFC 8785 body hash include no future pointer;
- codex runtime object/parent/receipt equals the local resume event;
- GitHub repository/object OID/receipt equals the candidate and frozen
  publication authority;
- provider readback repeats before pointer/publication use;
- logs, labels, prose, summaries, and free-text hashes have no identity
  authority;
- mismatch, stale authority, null error, replay, or readback change fails typed;
  and
- external binding alone creates no approval or current state.

## Required v8 Non-Regression Recheck

Return an explicit result for every v8 acceptance section:

- V8-I1;
- V8-I2 local-byte identity/import/readback;
- V8-D1;
- V8-L1 semantic reviewer-resume guarantees;
- V8-P1;
- V6-R1;
- V6-R2;
- V7-A1;
- preserved v6 contracts; and
- all v8 public negative plans.

The only legal substitutions are V9-R1 construction order and V9-R2 external
binding/source-kind ownership.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V9_R1=pass|fail
V9_R2=pass|fail
v8_retained_contracts=pass|fail
implementation_authorization=blocked|eligible_for_separate_source_stage
```

`APPROVE` is valid only when V9-R1, V9-R2, and every retained v8 contract pass
against the exact target bytes.

## Expected Commit Scope

The design-only successor commit must have direct parent
`0c5bfb817f1db7c0dee2026f9938ebe7139bb4eb` and exactly:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v9.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v9.md
```

Any source, test, owner-document, hook, config, workflow, skill, eval, prior
artifact, or unrelated path change is:

`design_only_scope_violation`.
