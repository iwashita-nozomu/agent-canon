# test-design
<!--
@dependency-start
contract skill
responsibility Designs runtime regression tests only for unresolved test-owned behavior risk.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/semantic-responsibility-contract.md semantic obligation and verification-owner contract
upstream design ../../documents/design/responsibility-rationale.md regression-test admission rationale
upstream design ../../documents/conventions/coding-conventions-testing.md reproduction evidence placement and lifecycle
@dependency-end
-->

## Purpose

Use `test-design` after the owning contract and implementation mechanism are known, and only when a concrete runtime behavior risk is not already closed by static analysis, an existing checker, type/lint/docs validation, or focused integration evidence. Tests are discriminators for behavior; metadata completeness is not the oracle.

## Activation

Return `required` only when all of the following are true:

1. the contract/public behavior is known;
2. the relevant implementation/state transition/error path is reachable;
3. a concrete failure could survive the already-selected validation owners;
4. a stable decidable observable can distinguish the correct behavior from that failure.

Otherwise reuse the existing validation owner or defer to the missing contract/implementation owner. Do not create a test plan or negative receipt for an unselected test responsibility.

## Minimal test admission

Each proposed regression case needs only:

- `contract`: the public/semantic behavior being protected;
- `counterexample`: a reachable failing input/state sequence, or an already-observed reproduction;
- `oracle`: a stable observable result that distinguishes the bad implementation from the accepted behavior.

A five-stage `Design Clause -> Mechanism -> Breaking Input -> Observable -> Oracle` packet is optional evidence for complex or ambiguous algorithms/state machines, not a universal requirement.

Existing reproduced failures, public failing inputs, issue reproductions, and deterministic integration failures are themselves reachability evidence. Do not require an additional null-hypothesis document for them. Use an explicit reachability witness only when the candidate may be unreachable from supported public behavior.

For reproduction placement, Issue permalinks, before/after evidence, and
post-fix consolidation, consume
[Bug reproduction evidence](../../documents/conventions/coding-conventions-testing.md#22-bug-reproduction-evidence).
Preserving a reproduction does not activate this skill or require an additional
per-Issue test when the existing validation owners already close the risk.

## Contract-derived behavioral tests

Code, including test code, executes the conditions, operations, and state
transitions that are written; names, comments, and intentions do not supply
missing behavior. Read the implementation to find how it can violate the
contract, not to define what the expected result must be.

1. Derive expected results from the approved contract, a mathematical property,
   or an independently justified reference. Explain that basis in the existing
   `oracle`; do not copy the production algorithm or bless its current output
   as the sole correctness oracle. Include required behavior absent from the
   implementation, not just branches that already exist.
2. Trace the actual input-to-observable path and choose the smallest inputs or
   state sequences that expose a concrete wrong condition, missing operation,
   or incorrect state update. Use contract-relevant boundaries, error paths,
   and side effects rather than nominal examples alone; do not freeze private
   implementation details or demand every category for every test.
3. Exercise the owning implementation at the selected observation level.
   Fixtures must reach the target behavior; mocks may isolate dependencies but
   must not replace the logic under test. An assertion only about a canned mock
   result does not validate that logic. Check real wiring when that boundary
   owns the unresolved risk.
4. Confirm that the selected case is collected, runs, and reaches its assertion.
   For a reproduced bug, replay the same input and oracle before and after the
   fix. If discrimination is otherwise unclear, use a small intentional fault
   such as a reversed condition, omitted update, or constant result. The
   assertion must reject the target contract violation, not an unrelated setup
   failure; skips, no-crash results, and coverage alone are not correctness
   evidence. A pass supports only the exercised contract, not all intentions.

For example, an integer-range contract `0 <= n < 3` accepts `0` and `2` and
rejects `-1` and `3`. These contract-derived expectations distinguish an omitted
lower bound, `<` changed to `<=`, and unconditional acceptance or rejection;
computing expected values with the same faulty predicate would hide the bug.

Apply this reasoning within `contract / counterexample / oracle`; do not add a
mandatory packet, mutation-testing framework, or redundant regression suite.

## Regression evidence ownership

[Minimal test admission](#minimal-test-admission) の `contract / counterexample / oracle` を、
変更責務の canonical invariant と最小の完全な owner に結び、最小 witness で表します。
期待値の根拠と assertion の識別力は [Contract-derived behavioral tests](#contract-derived-behavioral-tests)
に従います。この共通条件は追加前の判断と review が参照し、[Activation](#activation) を広げません。

- witness は [SEP-07](../../documents/conventions/software-engineering-principles.md#reachability-and-remedy-necessity)
  に照らして対象入口で成立する入力・状態を使います。mock が入口の保証を無効化して作る
  架空状態だけを回帰根拠にしません。
- 同じ invariant の witness は、既存の property、table-driven / exhaustive finite-state check、
  semantic equivalence、public/canonical entrypoint の boundary acceptance へ統合します。
  同じ oracle を二重に保つ historical regression は統合・削除し、個別 bug ごとに増設しません。
- private field、temporary path、helper topology、storage layout、削除済み互換状態を
  contract 化しません。正しい alternative implementation でも同じ semantic contract を判定します。
- parser、classifier、state construction、lifecycle、environment setup を production owner と
  別に test 側へ再実装しません。局所 algorithm が独立した数理的・工学的 contract owner なら、
  owner-local unit/property test は保持できます。

focused test は再現、原因分離、repair diagnosis の証拠です。handoff / completion は変更責務が
選んだ canonical boundary / acceptance oracle で判断し、実行不能なら focused pass で代用せず
remaining verification を残します。test、fixture、mock、test-only adapter の追加数、coverage、
mutation score、historical bug 数を単独の進捗・品質・完了条件にしません。
既存の task packet / design trace に判断を接続し、新しい schema、checker、必須帳票は作りません。

## Validation failure response

When a selected check fails, classify the `failing contract`, `observation level`,
`failure cause`, `approved intent`, and `evidence` before simplifying behavior,
deleting a test, weakening an oracle, or reverting a requested change. Record the
fields `failing_contract`, `observation_level`, `cause_classification`,
`intent_preservation`, and `evidence`, using
`documents/runtime/runtime-profiles-and-check-matrix.json` and its Markdown reader
projection. A stable implementation bug goes to the `owning code` after
classification; it does not need an `extra test-design pass`, and preserving
approved intent means `intent を弱めません` and does not use oracle weakening as
the repair.

## Numerical test admission

For numerical, randomized, tolerance, solver, convergence, residual, benchmark,
or experiment-style tests, apply the conditional Numerical Test Admission Gate
only when `activation=required`: consult
[documents/conventions/coding-conventions-testing.md](../../documents/conventions/coding-conventions-testing.md), record the `数値 trigger`,
numerical trigger,
non-numerical alternative, oracle, GPU target, and budget, and omit the numerical
test with an omission reason when the target behavior is not numerical. Do not
use a CPU computational test as a fallback for numerical validation.

## Rejection rules

Reject or redesign tests whose only oracle is no-crash, private call order, exact helper layout, internal implementation shape, arbitrary fixture completeness, or behavior already fully decided by a cheaper canonical static checker. Do not weaken production behavior merely to satisfy a historical test.

## Expected outcome

When activated, add the smallest case that fails under the demonstrated counterexample and passes under the public/semantic contract. Complex cases may attach additional mechanism traces when they improve reviewability. Completion is determined by discriminating power, not by fixed packet fields.
