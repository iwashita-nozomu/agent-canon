# test-design
<!--
@dependency-start
contract skill
responsibility Designs runtime regression tests only for unresolved test-owned behavior risk.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/semantic-responsibility-contract.md semantic obligation and verification-owner contract
upstream design ../../documents/design/responsibility-rationale.md regression-test admission rationale
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

## Rejection rules

Reject or redesign tests whose only oracle is no-crash, private call order, exact helper layout, internal implementation shape, arbitrary fixture completeness, or behavior already fully decided by a cheaper canonical static checker. Do not weaken production behavior merely to satisfy a historical test.

## Expected outcome

When activated, add the smallest case that fails under the demonstrated counterexample and passes under the public/semantic contract. Complex cases may attach additional mechanism traces when they improve reviewability. Completion is determined by discriminating power, not by fixed packet fields.
