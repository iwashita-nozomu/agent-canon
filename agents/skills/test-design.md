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

## Procedure

1. Read the changed implementation, contract, reachable state transition, and
   already-selected validation. Activate this skill only when a concrete runtime
   behavior risk remains open and a stable observable can distinguish correct from
   incorrect behavior.
2. Derive the smallest case from the contract or an independently justified
   reference. Trace its real input/setup-to-observable path; fixtures and mocks
   must reach the owning logic rather than replace it.
3. Keep the existing test oracle and wiring when they are correct. Do not change
   expected values, include/import paths, configuration, fixture data, or skips just
   to make a test pass. Update a test only for an established API/layout/spec
   migration or when source evidence shows the test itself is wrong; record the
   reason in the existing Issue/PR record.
4. Run the focused test through its existing owner. A reproduced failure is useful
   evidence; a pass proves only the exercised contract. If the failure is in the
   implementation, repair the owning code first rather than adding a wrapper or
   weakening the oracle.
5. For numerical/tolerance/solver/benchmark tests, use the existing numerical test
   owner and oracle, honoring the project-configured CPU/OpenMP or GPU route. Do
   not invent a fallback route or new admission packet.
6. Reuse an existing property/table/integration case when it already distinguishes
   the same invariant. Add one minimal regression case only when the risk remains
   uncovered, then review the final diff and record the test commit SHA and actual
   result in the existing delivery record.

## Boundary

Tests are evidence for behavior, not metadata completeness, coverage counts, private
layout, no-crash results, or a replacement for the owning checker. Do not add a new
schema, mutation framework, approval gate, ledger, or mandatory test plan.
