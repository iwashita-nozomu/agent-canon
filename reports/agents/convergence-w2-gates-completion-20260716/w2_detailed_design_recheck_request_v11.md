# W2 Detailed-Design v11 Fixed-Byte Recheck Request

## Request Identity

```text
request_schema=agent-canon.fixed-byte-design-review-request.v1
review_kind=independent_detailed_design_recheck
requested_decision=APPROVE|REVISE
implementation_authorization=blocked
finding_ids=V11-M1,V11-R1,V11-E1,V11-P1
owner_unit=validation evidence only
```

This request asks an independent reviewer to evaluate only the exact v11 design
bytes identified below. It authorizes no source implementation, tests, owner
documents, hooks, Python, CI, dynamic graph, publication, compatibility route,
new validation receipt ledger, or hand-written pass artifact.

The reviewer identity must differ from the design writer. Parent remains
monitor/integrator. A REVISE result returns findings to the same writer context
under the retained v10 reviewer-lineage contract; it does not authorize a
fresh reviewer or older candidate.

This request contains no identity for its own bytes, blob, containing commit,
tree, or size.

## Exact Review Target

```text
target_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v11.md
target_size_bytes=72413
target_sha256=fa98c755382ad5e401db6a878907cf04f086fdd9c719e264429d5a4db06fd406
target_git_blob=6823aae2f1a4d3f19da150b4e39ed86d0ef48938
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

## Bound v10 Predecessor

```text
predecessor_commit=26b77aa9b1cebf731c603558a468245a0795e923
predecessor_tree=6f0116751a84d5d1944a2a58caebfbff75c9774d
predecessor_parent=f46e5214e8554dbb4d5a03e745cdf8ecf41d6f20
predecessor_design_path=reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v10.md
predecessor_design_size_bytes=70791
predecessor_design_sha256=4ee788cce9d0b100b607e3d3f9637feae06f5ab3cd5e80dda5fe536872b23693
predecessor_design_git_blob=23a3431fcacdb34504c01c07431754d2c94df9e1
predecessor_request_path=reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v10.md
predecessor_request_size_bytes=8853
predecessor_request_sha256=8ea1424811d95d4cea4779096937520bbf76935258c6b630d7ff3530a24f6abf
predecessor_request_git_blob=862e1af6ade8c85230986fc7c1ce03b03702ebf2
```

v11 is an append-only delta over this exact v10 packet and its incorporated
v9/v8 packet.

## Bound Review Input

```text
review_input_kind=explicit_user_simplification_and_observed_validation-evidence defect
durable_decision_artifact=not_supplied
finding_count=4
finding_1=V11-M1
finding_2=V11-R1
finding_3=V11-E1
finding_4=V11-P1
```

No review artifact path, hash, blob, or decision may be invented.

## Required V11-M1 Recheck

Verify:

- validation evidence reuses the existing canonical run-bundle/result-artifact
  materializer;
- L remains the sole state authority;
- the existing `agent-canon.canonical-evidence-event.v1` five-status union and
  `agent-canon.ledger-transaction.v1` are reused;
- begin and settle are two uses of one generic
  `result_artifact_attempt_transition`, not a validation receipt side path;
- the transaction retains expected-head CAS, immutable members, O_EXCL temp
  recovery, fsync/rename/directory fsync, deterministic replay, and complete
  post-readback;
- one current-attempt pointer exists per exact logical key;
- pointer records contain no status or stored success value;
- pending, pass, fail, deferred-by-user, and not-applicable semantics remain
  exhaustive;
- raw/manifest artifacts are run-local, append-only, unique, and immutable;
- no `ValidationExecutionReceipt`, receipt ledger, current-receipt selector,
  standalone `validation_runner.py`, mutable latest file, compatibility reader,
  or test-only evidence injection remains; and
- crash, retry, stale-attempt, duplicate, gap, replay, and CAS conflicts are
  typed and fail closed.

## Required V11-R1 Recheck

Verify:

- exactly one `agent-canon.registered-validation-route.v1` record is frozen for
  one attempt;
- the complete top-level key set is exact;
- aggregate revision, logical key, attempt ordinal, current intent, candidate
  ID/revision/body/commit/tree/diff, and owner source identities are exact;
- `python.ruff.full` uses the exact ordered non-quick argv with source roots
  `python` then `tests`;
- argv is an actual UTF-8 array with no shell-string interpretation;
- cwd is the exact clean true-clone root and records absolute, repository, and
  repo-relative identity;
- the environment is the exact empty-base six-entry profile with no ambient
  inheritance;
- route ID seed and RFC 8785 body hash include every required identity and no
  future result/event/transaction/pointer;
- the route is derived from L, Git, active profile, tool catalog, wrapper, and
  executable readback;
- the public API accepts no candidate, argv, cwd, environment, expected status,
  output, producer, path, hash, or blob override; and
- missing roots, quick mode, reordered argv, stale owner source, duplicate
  route, or caller override fails typed.

## Required V11-E1 Recheck

Verify:

- executable identity is one closed union with only `repo_path_blob` and
  `external_resolved_file_bytes`;
- executable chain order and role set are exact;
- repo mode/blob/bytes and clean-clone readback are complete;
- external resolution records final regular-file path, device, inode, mode,
  size, mtime, and SHA256 from stable complete bytes;
- `python -m ruff` binds both the Python launcher and `ruff.__main__` origin;
- launcher/module identities are reread before version, before validation, and
  after validation;
- version policy is exactly `required_command` or owner-declared
  `unsupported_executable_identity_only`;
- the exact `python.ruff.full` route uses `required_command`;
- version outcome has one common complete key set and exactly three variants:
  captured, unsupported, or failed;
- captured outcome requires exit 0, complete selected-stream bytes, empty other
  stream, and exact `utf8_single_line_terminal_lf_v1` normalization;
- normalization rejects BOM, NUL, CR, embedded/missing/extra LF, multiple
  lines, and leading/trailing ASCII space or tab;
- unsupported outcome is legal only from exact owner authority and has all
  command/result fields present as null;
- failed outcome has one closed failure class, complete available raw bytes,
  null normalized text/hash, and forces validation fail;
- validation command termination, complete stdout/stderr, combined-output
  framing/hash, clean clone, and executable readback preserve v10 evidence
  strength; and
- every schema, null, resolution, identity, version, normalization, termination,
  and output mismatch has a typed public negative.

## Required V11-P1 Recheck

Verify:

- automatic review and publication derive the exact active-profile required
  route set;
- each route resolves exactly one unique current terminal attempt for the
  current candidate;
- the terminal event is reachable from the canonical materializer settlement
  transaction and exact current pointer;
- route record, generic manifest, raw artifacts, candidate, producer,
  executable, version, termination, output, and readback all recompute;
- manifest `stored_status` and event status are projection-only;
- gate-eligible producer is `change_reviewer` or `final_reviewer` and differs
  from the candidate writer;
- manager precheck, writer output, copied Ruff output, report text, emoji,
  checkboxes, PR text, and CI-only conclusions cannot pass;
- a new candidate/profile/route revision or later independent failure makes old
  pass evidence stale;
- no public review/publication API accepts a receipt or manifest path;
- review and publication reread exact provenance immediately before decision
  binding, network mutation, and publication CAS;
- materializer pass never creates review APPROVE;
- only explicit independent APPROVE plus complete current provenance unlocks
  publication; and
- every missing, pending, fail, stale, foreign, writer, hand-written, or
  contradictory attempt keeps publication locked with typed evidence.

## Required v10/v9/v8 Non-Regression Recheck

Return an explicit result for:

- V10-L1 local event authority;
- V10-X1 external projection acknowledgement;
- the five-stage DAG
  `intent -> frame -> event -> external acknowledgement -> current pointer`;
- v9 one-way immutable identity/write order;
- v8 artifact identity/import/readback and corrected source packet;
- reviewer lineage, compaction-safe same-context resume/replacement, no fresh
  or self-review bypass;
- automatic review from canonical workflow state, not keywords, prompts, or
  CI-only inference;
- exact candidate-OID publication independent of dirty worktree state;
- publication route inventory and expected-old-OID CAS;
- immutable candidate, intent revision list, and one current intent pointer;
- canonical ledger sole authority and pure projections;
- per-member source-event correspondence and exact group equality;
- D2 branch reason and D3 cross-member owner/state/API/dependency/responsibility/
  outcome/evidence equality;
- exact freeze/topology predicates;
- five formatter statuses and pending/deferred validation honesty;
- no self-referential object;
- no compatibility/test-only API; and
- all retained public negative oracles.

The only legal substitution is v11's replacement of v10 `V10-V1`.

## Review Output Contract

Return findings first. Every finding includes priority, exact section/line
evidence, violated clause, required repair, intent preservation, issue route,
and re-review requirement.

Then return:

```text
decision=APPROVE|REVISE
V11_M1=pass|fail
V11_R1=pass|fail
V11_E1=pass|fail
V11_P1=pass|fail
v10_v9_v8_retained_contracts=pass|fail
implementation_authorization=blocked
reviewed_target_path=<exact target path>
reviewed_target_size_bytes=<recomputed size>
reviewed_target_sha256=<recomputed SHA256>
reviewed_target_git_blob=<recomputed Git blob>
reviewer_identity=<independent reviewer identity>
review_artifact_path=<external review artifact path>
```

APPROVE requires every listed result to pass. The review artifact must not
contain its own complete-file SHA, Git blob, containing commit, or tree.
Those identities are materialized externally after review bytes are fixed.

## Scope And Validation Boundary

The reviewed v11 commit must change exactly:

```text
reports/agents/convergence-w2-gates-completion-20260716/w2_f1_f6_repair_design_v11.md
reports/agents/convergence-w2-gates-completion-20260716/w2_detailed_design_recheck_request_v11.md
```

Expected design-author validation is:

```text
tools/bin/agent-canon docs format <the exact two paths>
tools/bin/agent-canon docs check <the exact two paths>
git diff --check -- <the exact two paths>
Git size/SHA256/blob readback
```

OOP/SOLID, registered route execution, materializer transaction execution,
Python quality checks, public negative tests, and publication integration
remain typed pending. Source implementation remains blocked until this exact
v11 target receives independent APPROVE.
