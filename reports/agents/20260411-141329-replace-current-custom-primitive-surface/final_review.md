# Final Review

- Run ID: 20260411-141329-replace-current-custom-primitive-surface
- Task: replace current custom primitive surface with raw ABI primitive contract integrated with Kokkos and Enzyme
- Owner: codex

## Ship Blockers

| Finding | Severity | Status |
| ------- | -------- | ------ |
| none | none | clear |

## Design Trace Acceptance

- design trace remains intact: runtime/compiler docs, design brief, and test plan all point to raw ABI primitive as the canonical user-defined derivative boundary.
- implementation maps cleanly to those artifacts:
  - public contract: `include/native_autodiff/native_autodiff.hpp`
  - Enzyme raw hook wiring: `include/native_autodiff/detail/raw_primitive_enzyme_impl.hpp`
  - root smoke: `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`
  - installed package consumer: `tests/cpp/package_consumer/main.cpp`
  - Kokkos adapter smoke: `tests/cpp/backend_dependency_consumer/main.cpp`

## Planned Work Completion Review

- planned work units for this run are complete:
  - legacy scalar custom primitive public path removed
  - raw ABI primitive helper and hook registration added
  - Kokkos wrapper->raw same-code smoke added
  - docs rewritten to raw ABI canonical path
  - validation gates passed

## Spec-To-Product Coverage Review

- `M1` / `E1` / `E3`: raw ABI contract and Kokkos adapter evidence live in header/docs/root smoke/package consumer/backend consumer.
- `M2` / `E2`: scalar `custom_primitive(...)` public path is gone from header/docs/tests.
- `M3` / `E4`: Enzyme path remains compile-time only; root and package binaries still pass no-runtime-symbol checks.
- `M4` / `E5`: subagent review ran before implementation and repo-native validation passed.

## Review Finding Incorporation Review

- subagent findings about compile break, stale package consumer, and stale docs were fixed.
- follow-up guidance about the exact Kokkos raw adapter pattern was incorporated into backend consumer.
- no fix-now finding remains only in review text.

## Residual Risks

- current raw helper is intentionally narrow: scalar `double` return and one-or-two raw arguments, which covers the current `ptr + extent` canonical path but not richer descriptor ABIs yet.
- low-level tensor `custom_elementwise` remains as backend-facing compatibility machinery, not as the canonical user-facing derivative protocol.
