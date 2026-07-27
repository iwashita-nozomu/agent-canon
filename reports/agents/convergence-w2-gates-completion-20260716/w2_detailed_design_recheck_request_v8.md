# W2 Detailed-Design v8 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V8-I1,V8-I2,V8-D1,V8-L1,V8-P1
```

This request asks an independent reviewer to evaluate only the exact v8 design
bytes identified below. It does not authorize source implementation, tests,
owner-document changes, hooks, Python, CI, dynamic graph execution,
publication, checkout cleanup, automatic approval, or self-review.

This request intentionally contains no identity for its own complete bytes,
Git blob, containing commit, tree, or byte size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v8.md
target_size_bytes=205113
target_sha256=7c310a2befb32290781a42ab9b2043b405a18da5cecf6598784c10096519659a
target_git_blob=f1d612ae990ad9b810cef475992a6e6873c68118
target_encoding=UTF-8
target_bom=absent
target_line_endings=LF
target_identity_authority=canonical_tool_readback
```

Before reviewing content, independently recompute byte size, SHA256, and Git
blob from the exact target bytes. Any mismatch is:

`review_target_identity_mismatch`.

Do not review a reformatted, copied, regenerated, summarized, or
chat-transcribed version. The target fields are mechanically inserted from
readback after canonical formatting; they are not approval authority.

## Bound v7 Predecessor

```text
predecessor_commit=3fab576c1bf1a4621ae69778859b441fbaf7bda9
predecessor_tree=78e8c5840660d80e748106f7e9e2966fc59b4d1f
predecessor_parent=772883acd2dbc6d0eab70fb789d0a73a4ed5a8b9
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v7.md
predecessor_design_size_bytes=134458
predecessor_design_sha256=2a0df1aec3f2fbe8ec2d717ddf1ee8d8c29beadc27855f9631d34acc6b17d270
predecessor_design_git_blob=76f04266d33bdb613a7606d5a731c9ad917f61a3
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v7.md
predecessor_request_size_bytes=11576
predecessor_request_sha256=f174257b3bf40c0b46784d2dce981b87b85d3eeccf14be845232ffc76816f93d
predecessor_request_git_blob=ed55a91ebbb912b6860209829aad1d2c7b8e0bdd
```

v8 must be an append-only design successor of this exact commit. v7 behavior
remains normative except where one of the five v8 finding clauses explicitly
replaces it.

## Bound Review Input

```text
review_input_kind=explicit_user_revise_packet
durable_v7_decision_artifact=not_supplied
finding_count=5
finding_1=V8-I1
finding_2=V8-I2
finding_3=V8-D1
finding_4=V8-L1
finding_5=V8-P1
```

No decision artifact path, hash, or blob may be invented. The five explicit
clauses are the review input; this fixed-byte request is the durable v8 reviewer
entrypoint.

## Required V8-I1 Recheck

Verify:

- the committed v6 request path is exact;
- size is `5662`;
- SHA256 is
  `f7ac2ca13caaea2c9668d9ad62ea3903a336dbf3b9fddf77308b47602060ca55`;
- Git blob is exactly
  `6ff0191daf02f86b6642bfb2762db6ccc702fdbe`;
- every v8 source packet, trace, acceptance predicate, and request occurrence
  uses that identity;
- the stale v7 prose identity is never selected after v8; and
- v7 remains unchanged as append-only history.

## Required V8-I2 Recheck

Verify:

- `COMMUNICATION_PROTOCOL.md` owns one exact
  `agent-canon.artifact-identity.v1` schema;
- one replaceable `artifact_identity.py` materializer/readback tool computes
  size, SHA256, Git blob, source tuple, mode, encoding, BOM, line endings, and
  stable file readback;
- its APIs accept no claimed identity or success values;
- source-binding variants and null/non-null rules are exhaustive;
- Git blob byte construction, record ID seed, RFC 8785 record hash, and
  non-self-reference are exact;
- review/publication packets import the structured record rather than
  transcribing free-text values;
- packet import hash and typed equality are complete;
- review dispatch rereads target bytes before dispatch;
- GitHub/publication paths reread decision, receipt, authority, source packet,
  and candidate identities before any network/ref/PR side effect;
- a transposed approval SHA, manual SHA field, stale path, byte race, mode/blob
  swap, foreign candidate, or import mismatch fails typed; and
- mismatch blocks before push, `gh`, PR API, ref update, or merge.

## Required V8-D1 Recheck

Verify the four exact root `README.md` pairs:

1. README to `check_convention_compliance.py` and its inverse;
2. README to `tool_drift.py` and its inverse;
3. README to `test_check_convention_compliance.py` and its inverse; and
4. README to `test_tool_drift.py` and its inverse.

Also verify:

- direction, `implementation` kind, relative path, and reason bytes are exact;
- existing tool/test pairs remain;
- the prompt-eval test remains connected through the critical eval owner;
- convention/drift tools enforce direct and reverse lines;
- tests cover missing direct, missing inverse, kind mismatch, path mismatch,
  and conflicting duplicate; and
- no durable header points to this run-local v8 packet.

## Required V8-L1 Recheck

Verify:

- L's current reviewer locator remains selection authority;
- runtime inventory is observation evidence only;
- terminal status is exactly `completed`, `errored`, or `shutdown`;
- timeout, empty wait, absent response, missing/ambiguous/foreign/stale ID is
  not terminal authority;
- legal modes are exactly provider resume of the same runtime ID or
  owner-selected replacement under the same assignment;
- evidence refs, owner evidence order, same-context fingerprint, clause/source
  packet/acceptance hashes, authority receipt, frame v2 `resume_transition`,
  event ID seed, and event schema are exact;
- no result runtime ID participates in the pre-dispatch event ID;
- event body serialization is RFC 8785 and non-self-referential;
- resume mode returns the same runtime ID and replacement mode returns a
  different runtime ID;
- reviewer remains distinct from writer and parent;
- event, current locator, and `dispatch_pending -> dispatched` transition are
  atomic;
- failed dispatch advances neither event nor locator;
- post-readback equality is complete; and
- fresh reviewer, reassignment, self-review, prompt, keyword, CI, or parent
  decision bypass fails typed.

## Required V8-P1 Recheck

Verify:

- the current approved candidate commit/tree is sole publication source
  authority;
- HEAD, branch, index, worktree, staged, untracked, merge, and summary state
  are observations only;
- dirty checkout publication uses only an exact candidate-OID local
  operation/remote refspec/owner PR tuple;
- a route unable to name the exact OID requires a separate clean standalone
  true clone;
- true-clone `.git`, common-dir, alternates, HEAD, index tree, and status
  predicates are exact;
- the checkout-authority schema, route enum, status/path hashes, ID seed,
  forbidden mutation set, and body hash are complete;
- publication never adds, commits, resets, restores, cleans, stashes, reverts,
  checks out, merges, copies, includes, or discards unrelated changes;
- dirty checkout status bytes remain unchanged across publication;
- expected-old target and post-readback equal the candidate OID; and
- implicit source, auto-include/revert, refspec, clone identity, object,
  authority, concurrency, or readback mismatch fails typed.

## Required v7 Non-Regression Recheck

Return an explicit result for:

- V6-R1 total route, raw literal, seven caller, and dependency closure;
- V6-R2 deterministic `O_EXCL` recovery;
- V7-A1 canonical automatic independent review;
- pre-review candidate attestation;
- independent review receipt bound to immutable B;
- post-APPROVE publication authority;
- immutable B/source/intent rows and one current pointer;
- expected-old local/remote/PR CAS and post-readback;
- checked-out-target refusal;
- canonical ledger sole authority and pure projection;
- exact per-member source correspondence and cross-member equality;
- exhaustive five formatter statuses and closed transitions;
- D2, D3, F1, and F2;
- exact freeze/topology/repair/escalation predicates;
- canonical tree-delta serialization;
- convention closure including `check_convention_consistency.py`;
- non-self-reference;
- no compatibility selector or test-only production API; and
- no long-prompt, keyword, CI-only, self-review, or automatic-approval route.

## Review Output Contract

Return findings first. Every finding must include:

- priority;
- exact artifact section/line evidence;
- violated finding/clause;
- required design repair;
- intent preservation;
- issue route; and
- whether re-review is required.

Then return:

```text
decision=APPROVE|REVISE
V8_I1=pass|fail
V8_I2=pass|fail
V8_D1=pass|fail
V8_L1=pass|fail
V8_P1=pass|fail
V6_R1=pass|fail
V6_R2=pass|fail
V7_A1=pass|fail
retained_contracts=pass|fail
implementation_authorization=blocked|eligible_for_separate_source_stage
```

`APPROVE` is valid only when all five v8 findings, V6-R1, V6-R2, V7-A1, and
every retained contract pass against the exact target bytes.

## Expected Commit Scope

The design-only successor commit must have direct parent
`3fab576c1bf1a4621ae69778859b441fbaf7bda9` and exactly these changed paths:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v8.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v8.md
```

Any source, test, owner-document, hook, config, workflow, skill, eval, prior
artifact, checkout cleanup, or unrelated path change is:

`design_only_scope_violation`.
