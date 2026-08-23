# change-review
<!--
@dependency-start
contract skill
responsibility Reviews changed code/docs/generated surfaces findings-first and escalates only durable follow-up work.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design ../../documents/design/responsibility-rationale.md durable finding and OOP-review activation rationale
upstream design ../../documents/conventions/software-engineering-principles.md contract-first review precedence and evidence model
upstream design ../../documents/conventions/common/03_comments.md decision-comment review policy
upstream design ../../issues/README.md durable issue and GitHub mirror policy
upstream design ../internal-routines/design-implementation-correspondence.md forward/reverse design correspondence and drift block route
@dependency-end
-->

## Related Document Closure

The review packet consumes the active DIC-010 path+section+clause/ref closure receipt. DIC owns closure traversal; this skill records the changed-path reverse trace, design fingerprint, owner mapping, implementation target, and validation-route readback. Missing or drifting DIC-010 coverage blocks acceptance rather than creating a second correspondence policy.

## Purpose

Review the actual diff and selected validation evidence findings-first. Findings must be grounded in reachable behavior, contract/design drift, or a concrete maintenance/safety failure; broad style preferences are non-blocking guidance.

## Software Engineering Principle Review

Use [ソフトウェア工学原則](../../documents/conventions/software-engineering-principles.md)
as the canonical precedence and evidence model. A material finding names the concrete user/domain
contract, semantic invariant, state/lifecycle owner, dependency or authority boundary, reachable
failure, testability loss, or traceability break that the changed surface creates. A principle name
alone is not a finding.

Review only principles that can change the decision for the actual diff. Do not require a KISS,
YAGNI, DRY, SOLID, determinism, or traceability checklist for every PR, and do not emit
`not applicable`, negative receipts, or empty principle sections. When principles conflict, apply
the canonical order: contract/correctness and invariant ownership before root-cause closure,
responsibility boundary, verification, simplicity, and style.

Typical review misuse to reject:

- treating textual similarity as DRY evidence when meaning, unit, stop condition, owner, or failure semantics differ;
- treating shortest code or minimum diff as KISS when error, migration, cleanup, or root mechanism remains open;
- treating YAGNI as permission to leave requested behavior or consumer migration incomplete;
- introducing a speculative interface, registry, wrapper, checker, or receipt without a concrete caller or responsibility gap;
- applying OOP/SOLID to a change that does not materially alter an object contract.

This skill records the selected clause and task-specific evidence; it does not reproduce the general
policy or add a second principle trigger table.

## Repeated Responsibility Review

When the changed reachability contains two or more independently editable sites that appear to own
the same responsibility, evaluate whether that responsibility needs one canonical owner or a stable
shared abstraction. Let `S(R)` be the independently editable implementation sites for responsibility
`R`; observing `|S(R)| >= 2` activates this assessment, but does not by itself create a finding or
require extraction.

Treat sites as the same responsibility only when evidence aligns on the material dimensions:

- change reason;
- semantic invariant or policy;
- lifecycle or effect owner;
- failure semantics;
- caller contract.

Textual similarity, shared syntax, or a repeated helper shape is not sufficient. Conversely, syntax
may differ while the responsibility is still duplicated when the sites independently encode the
same policy or invariant for the same callers and change reason.

A repeated-responsibility finding is material only when evidence shows at least one concrete risk:

- a change to `R` requires synchronized edits at multiple sites;
- multiple sites act as independent authorities for the same invariant or policy;
- the sites can drift independently and produce observably inconsistent behavior.

Prefer the simplest disposition that preserves the contract: delegate to an existing canonical
owner, extract a shared abstraction at a stable responsibility boundary that passes the canonical
abstraction-admission test, or retain separate implementations with evidence that domain meaning,
lifecycle, failure semantics, caller contracts, or change reasons differ. An abstraction that needs
caller-specific flags, branches, or privileged reach-around is evidence that the boundary is not yet
stable.

Start from the diff and evidence-linked sibling implementations; do not require a repository-wide
clone scan, a fixed rule-of-three threshold, a new checker, or a dedicated receipt. A material finding
identifies the repeated sites, the shared responsibility dimensions, the synchronization/authority/
drift risk, and the selected SEP-03 or SEP-08 clause that supports the decision.

## Code Comment Review

Use [コメント規約](../../documents/conventions/common/03_comments.md) as the canonical meaning and
lifecycle owner. Review changed comments and comments adjacent to changed logic; do not perform a
repository-wide comment-density audit merely because code changed.

A comment finding is blocking only when evidence shows one of the following concrete failures:

- a stale or misleading comment states an invariant, assumption, ordering, numerical condition,
  authority boundary, external constraint, or failure semantic that the current implementation no
  longer preserves;
- a material correctness, safety, numerical-validity, ordering/lifetime, external-contract, or
  compatibility decision cannot be recovered from names, types, structure, or canonical code and
  lacks the local rationale needed to avoid a plausible incorrect maintenance change;
- the diff changes logic covered by a decision comment but leaves the comment unsynchronized.

Issue/PR text does not substitute for local rationale needed at the code owner. Conversely, missing
comments on obvious assignments, branches, loops, simple properties, stubs, or self-explanatory
helpers are not findings. Comment count, line density, preferred wording, or a demand to restate the
implementation are non-blocking style preferences. Do not add a comment-count checker or checklist
receipt; tie every material finding to the concrete invariant and reachable maintenance failure.

## Finding model

For each material finding record enough to act on it: affected surface, evidence, impact/severity, current resolution, and the owning contract or selected engineering-principle clause when it affects the decision. Issue lifecycle is independent from finding validity.

Use a durable issue only when the finding outlives the current review: it belongs to another owner/scope, recurs, needs later work, or cannot safely be closed in the current diff. Findings fixed in the current change, questions, rejected hypotheses, duplicates, and accepted local resolutions do **not** need `issue_route`, a local issue file, or a GitHub mirror.

Remote mirror/publication follows the canonical issue policy; review does not perform remote reconciliation merely because a finding exists.

## Regression Evidence Review

新しい regression test、fixture、mock、test-only adapter を「再発防止が増えた」という理由だけで
肯定しません。変更された contract に対して、その evidence が canonical invariant の反例を固定して
いるか、それとも現在の representation を別の仕様として固定しているかを判定します。

material な regression 追加では、少なくとも次の evidence-linked question が判断可能であることを
確認します。専用 checklist receipt や checker を追加する必要はありません。

- どの canonical contract / invariant が failure により反証され、その owner はどこか。
- case はその invariant の minimal counterexample / witness になっているか。
- 既存 property、table-driven finite state、semantic equivalence、canonical boundary acceptance に統合できない理由があるか。
- private field、temporary path、helper topology、storage layout、deleted compatibility state を test の都合で contract 化していないか。
- parser、classifier、state builder、lifecycle、environment setup の第二実装を test 側に作っていないか。
- 同じ invariant を所有する historical regression を統合・削除して、一つの oracle に収束できないか。
- 正しい alternative implementation に置換しても、その test が semantic contract を同じように判定するか。

focused test の pass は counterexample の再現と repair diagnosis の evidence であり、それだけを
handoff / completion proof とみなしません。変更責務の canonical validation route が formal entrypoint、
consumer boundary、clean replay、environment acceptance 等を要求する場合、その oracle まで確認します。
実行不能なら verified completion へ昇格させず remaining verification として扱います。

逆に、局所 algorithm 自体が独立した数学的・工学的 contract owner なら owner-local unit/property test
は正当です。test count、coverage percentage、mutation score、historical bug 数を単独で品質尺度にして
追加を要求しません。

## OOP/SOLID activation

Delegate OOP/SOLID sensitivity to the canonical Python/OOP reviewer. Do not add OOP readability or SOLID evidence just because the changed path contains a class, dataclass, Protocol, annotation, parser model, or public type. Select it when inheritance/substitutability, dependency inversion, responsibility ownership, mutation/lifecycle, DI, or a public object model materially changes.

Do not duplicate a second SOLID-sensitive trigger table in this skill.

## Review order

1. Read base/head and the changed surface.
2. Read the owning contract/design, the material engineering-principle clause, and targeted validation evidence.
3. When the changed surface adds or changes a responsibility, inspect evidence-linked sibling implementations; if `|S(R)| >= 2`, evaluate canonical ownership, stable abstraction, or evidence-backed intentional separation.
4. Review changed comments and comments adjacent to changed logic for required local rationale, stale assumptions, and same-diff synchronization under the canonical comment policy.
5. When regression evidence changes, review its canonical invariant/owner, minimal witness, representation independence, duplicate truth, consolidation opportunity, and completion oracle before treating added test coverage as positive evidence.
6. Report blocking correctness/safety/design findings before summary.
7. Resolve current-scope findings in the current diff when possible.
8. Escalate only durable residual work to the issue owner.
9. State merge/acceptance readiness from unresolved blocking findings and required validation, not from issue-count, test-count, comment-count, or packet completeness.

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
1. 変更された責務ごとに evidence-linked sibling implementation を確認します。独立編集可能な同一責務が複数ある場合は、change reason、invariant/policy、lifecycle/effect owner、failure semantics、caller contract を照合し、canonical owner への委譲、安定した抽象化、または根拠ある分離を判定します。回数や textual similarity だけでは finding にしません。
1. 変更された code comment と、その comment が説明する近傍 logic を対応付け、共通コメント規約の必要条件、正確性、同一差分での同期を確認します。comment density や自明な説明の有無は finding にしません。
1. 変更面について、causal ambiguity または owner/fix/validation を変え得る
   alternative があるか判定します。該当する場合だけ cause-evidence note/receipt を作り、
   incoming callers/entrypoints、owning mechanism/state/guards、downstream
   consumers/side effects/cleanup、sibling implementations/tests/docs/config
   を evidence-linked にたどります。straightforward finding は direct cause proof
   を記録し、rejected/duplicate/already-covered/unreachable finding はその reason/evidence
   だけで閉じます。必要な場合だけ latest remote/Issue/branch history を確認します。
1. 選択した contract surface と material engineering-principle clause に対して docs と tests が追随しているか確認します。regression を追加した場合は、canonical invariant/owner と completion oracle への従属、第二 truth の不在、consolidation の有無も確認します。
1. 継承/substitutability、ownership/lifecycle、dependency inversion/DI、public object model、または typed boundary が material に変わる場合だけ `python-review` を追加し、`$oop-readability-check` と `check_solid_evidence.py` の evidence を review input にします。class、dataclass、`Protocol`、annotation、parser model、public type の存在だけでは OOP/SOLID を起動しません。
1. 数値・solver・tolerance・convergence・residual・benchmark の test 変更では、必要な場合だけ `test-design` の Numerical Test Admission Gate と `documents/conventions/coding-conventions-testing.md` を参照し、trigger、non-numerical alternative、oracle、budget を確認します。非数値の変更にはこの gate を追加しません。
1. まず static checks と targeted validation を実行し、full repository
   dependency review、full suite、remote CI は最終候補の契約が選択した場合だけ一度実行します。
1. findings を hypothesis として priority 順に並べ、current snapshot、reachable
   path、contract、witness/static proof を付けます。decision-owning reviewer または
   ship_reviewer が accept または reject を adjudicate します。
1. `required_action` または solution proposal は、activated finding では
   cause-evidence note/receipt の `Selected Cause` と `Expected Mechanism` から、
   straightforward finding では direct cause proof から導出します。各 finding に
   durable follow-up が必要な finding だけ `issue_route` を付けます。現在の
   review loop で閉じるものは issue route を要求せず、運用上残すものは既存
   `issues/open/` または新規 local issue、外部 triage が必要なものは
   `issue_sync.py` による GitHub mirror plan へ接続します。
1. summary は findings の後に短く付けます。

## Boundary

A review does not invent extra gates, tests, reports, principle checklists, comment-density checks, or durable lifecycle records merely to make its schema complete. Existing canonical validation and publication owners remain authoritative.
