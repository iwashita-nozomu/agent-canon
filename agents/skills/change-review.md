# change-review
<!--
@dependency-start
contract skill
responsibility Reviews changed code/docs/generated surfaces findings-first and escalates only durable follow-up work.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design ../../documents/design/responsibility-rationale.md durable finding and OOP-review activation rationale
upstream design ../../issues/README.md durable issue and GitHub mirror policy
upstream design ../internal-routines/design-implementation-correspondence.md forward/reverse design correspondence and drift block route
@dependency-end
-->

## Related Document Closure

The review packet consumes the active DIC-010 path+section+clause/ref closure receipt. DIC owns closure traversal; this skill records the changed-path reverse trace, design fingerprint, owner mapping, implementation target, and validation-route readback. Missing or drifting DIC-010 coverage blocks acceptance rather than creating a second correspondence policy.

## Purpose

Review the actual diff and selected validation evidence findings-first. Findings must be grounded in reachable behavior, contract/design drift, or a concrete maintenance/safety failure; broad style preferences are non-blocking guidance.

## Finding model

For each material finding record enough to act on it: affected surface, evidence, impact/severity, and current resolution. Issue lifecycle is independent from finding validity.

Use a durable issue only when the finding outlives the current review: it belongs to another owner/scope, recurs, needs later work, or cannot safely be closed in the current diff. Findings fixed in the current change, questions, rejected hypotheses, duplicates, and accepted local resolutions do **not** need `issue_route`, a local issue file, or a GitHub mirror.

Remote mirror/publication follows the canonical issue policy; review does not perform remote reconciliation merely because a finding exists.

## OOP/SOLID activation

Delegate OOP/SOLID sensitivity to the canonical Python/OOP reviewer. Do not add OOP readability or SOLID evidence just because the changed path contains a class, dataclass, Protocol, annotation, parser model, or public type. Select it when inheritance/substitutability, dependency inversion, responsibility ownership, mutation/lifecycle, DI, or a public object model materially changes.

Do not duplicate a second SOLID-sensitive trigger table in this skill.

## Review order

1. Read base/head and the changed surface.
2. Read the owning contract/design and targeted validation evidence.
3. Report blocking correctness/safety/design findings before summary.
4. Resolve current-scope findings in the current diff when possible.
5. Escalate only durable residual work to the issue owner.
6. State merge/acceptance readiness from unresolved blocking findings and required validation, not from issue-count or packet completeness.

## Conditional Cause Investigation Before Required Action

Cause investigation is conditional, not a universal review ceremony. Activate
the bounded investigation when causal ambiguity remains unresolved, or when an
evidence-linked alternative could change the owner, fix surface, or validation
route. For a straightforward finding where a type, schema, parser, compiler,
state invariant, or targeted reproduction establishes one cause, record a
compact direct cause proof and derive the action from it; no named receipt is
required. Rejected, duplicate, already-covered, and unreachable findings keep
their reason/evidence and do not acquire a cause receipt.

For an activated finding, a solution proposal MUST NOT be derived from the
symptom alone. Record a compact `Cause Investigation Receipt` (a cause-evidence
note). It has no fixed schema or candidate count; record the applicable
evidence needed to establish:

- `Observation`: the reproduced symptom or static observation, with the
  current source snapshot and exact entrypoint;
- `Incoming Callers/Entrypoints`: evidence-linked callers, dispatchers,
  parsers, public imports, workflow triggers, and configuration entrypoints
  that can reach the observation;
- `Owning Mechanism/State/Guards`: the state transition or mechanism that
  creates the behavior, including guard predicates, invariants, and any
  duplicated or over-strict checks;
- `Downstream Consumers/Side Effects/Cleanup`: consumers, writes, process or
  resource effects, error handling, rollback, and cleanup paths affected by
  the mechanism;
- `Sibling Implementations/Tests/Docs/Config`: comparable implementations,
  regression tests, documentation, and configuration that can confirm or
  disconfirm the ownership and contract;
- `Temporal Evidence`: latest remote/default branch, related issue/PR, or
  branch history when snapshot drift, a recent change, or a stale generated
  surface is plausible. This section is conditional, not a mandatory history
  sweep;
- `Reachability and Overcheck Analysis`: a proof or targeted observation for
  each disputed branch/guard. Record an unreachable branch as rejected with
  `reason_code=unreachable_branch`, and an unnecessary or duplicated guard as
  `reason_code=overcheck`, rather than proposing a test or repair for behavior
  that cannot occur;
- `Alternative Disposition`: each alternative that could change the owner,
  fix surface, or validation is either disconfirmed or explicitly bounded,
  with its evidence reference;
- `Selected Cause` and `Expected Mechanism`: the causal explanation and the
  state/mechanism change expected to remove the symptom;
- `Action Derivation`: the required action is derived from the selected cause
  and expected mechanism, and names the contract and validation it preserves.

These are evidence dimensions, not a ceremony checklist for every finding.
Mark an inapplicable dimension as such when that itself bounds the alternative;
do not manufacture a caller, side effect, sibling, or history search.

The activated investigation starts from the changed diff and expands through
evidence-linked incoming and outgoing edges. It does not require an arbitrary
full-repository scan or a fixed number of candidates. Stop only when every
alternative that could change the owner, fix surface, or validation has been
disconfirmed or bounded. If a static invariant or targeted reproduction proves
one cause, the direct-proof path is complete. For an activated finding, the
operation is complete at
`cause_hypothesis_selected -> action_derived_from_cause -> validation_route_bound`;
for a straightforward finding it is
`direct_cause_proof -> action_derived_from_cause -> validation_route_bound`.
`cause_unproven` applies only when ambiguity remains and blocks the action.

## Root-Cause Repair Scope After Cause Selection

After `Selected Cause` and `Expected Mechanism` are established (or after a
straightforward finding has a direct cause proof), the repair objective is
root-cause closure, not a minimum diff. `minimum-diff`, `smallest-local-patch`,
and `smallest patch` are explicitly prohibited as repair objectives. Select the
complete replaceable owning responsibility unit identified by the evidence,
even when that unit spans more than the file containing the symptom.

The selected unit is complete only when the root mechanism is closed and its
evidence-linked reachable consumers, side effects, failure handling, rollback,
and cleanup are covered. The repair also closes the affected contract, docs,
tests, and validation route. Keep this closure evidence-bounded: do not expand
into unrelated repository cleanup or historical tidying that cannot change the
selected owner, mechanism, consumers, contract, or validation.

Symptom suppression, a wrapper or compatibility shim that leaves the root
mechanism open, test-only relaxation or oracle weakening, and a nearby local
patch without root mechanism closure are repair failures. A smaller diff is
acceptable only when the evidence proves that the complete owning unit and all
reachable effects are fully closed; size is never the selection criterion.

The action reaches
`complete_owning_unit_selected -> root_mechanism_closed -> reachable_effects_closed ->
contract_docs_tests_validation_closed` before it can be accepted. A proposal
that stops at symptom suppression, a wrapper, test-only relaxation, or a nearby
local patch returns to cause/scope analysis rather than opening a repair wave.

## Default Sequence

1. `git diff --stat` と `git diff --name-only` で変更面を固定します。
1. 破壊的変更、削除、rename、config 変更を先に見ます。
1. 変更面について、causal ambiguity または owner/fix/validation を変え得る
   alternative があるか判定します。該当する場合だけ cause-evidence note/receipt を作り、
   incoming callers/entrypoints、owning mechanism/state/guards、downstream
   consumers/side effects/cleanup、sibling implementations/tests/docs/config
   を evidence-linked にたどります。straightforward finding は direct cause proof
   を記録し、rejected/duplicate/already-covered/unreachable finding はその reason/evidence
   だけで閉じます。必要な場合だけ latest remote/Issue/branch history を確認します。
1. 選択した contract surface に対して docs と tests が追随しているか確認します。
1. 継承/substitutability、ownership/lifecycle、dependency inversion/DI、public object model、または typed boundary が material に変わる場合だけ `python-review` を追加し、`$oop-readability-check` と `check_solid_evidence.py` の evidence を review input にします。class、dataclass、`Protocol`、annotation、parser model、public type の存在だけでは OOP/SOLID を起動しません。
1. 数値・solver・tolerance・convergence・residual・benchmark の test 変更では、必要な場合だけ `test-design` の Numerical Test Admission Gate と `documents/conventions/coding-conventions-testing.md` を参照し、trigger、non-numerical alternative、oracle、budget を確認します。非数値の変更にはこの gate を追加しません。
1. まず static checks と targeted validation を実行し、full repository
   dependency review、full suite、remote CI は最終候補の契約が選択した場合だけ一度実行します。
1. findings を hypothesis として priority 順に並べ、current snapshot、reachable
   path、contract、witness/static proof を付けます。parent / integration owner が
   accept または reject を adjudicate します。
1. `required_action` または solution proposal は、activated finding では
   cause-evidence note/receipt の `Selected Cause` と `Expected Mechanism` から、
   straightforward finding では direct cause proof から導出します。各 finding に
   durable follow-up が必要な finding だけ `issue_route` を付けます。現在の
   review loop で閉じるものは issue route を要求せず、運用上残すものは既存
   `issues/open/` または新規 local issue、外部 triage が必要なものは
   `issue_sync.py` による GitHub mirror plan へ接続します。
1. summary は findings の後に短く付けます。

## Boundary

A review does not invent extra gates, tests, reports, or durable lifecycle records merely to make its schema complete. Existing canonical validation and publication owners remain authoritative.
