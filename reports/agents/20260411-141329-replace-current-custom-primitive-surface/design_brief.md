# Detailed Design Brief

- Run ID: 20260411-141329-replace-current-custom-primitive-surface
- Task: replace current custom primitive surface with raw ABI primitive contract integrated with Kokkos and Enzyme
- Owner: codex

## Goals

- Replace the current scalar-expression custom primitive surface with a raw-ABI primitive contract whose canonical boundary is the raw function, not the Kokkos wrapper and not an internal scalar IR node.
- Keep Kokkos as an execution/runtime adapter only: `View` or wrapper code forwards to the raw ABI function body, and the same code body can be used from `Serial` and `DefaultExecutionSpace`.
- Keep Enzyme as the only AD engine: raw primitive metadata and explicit derivative hooks are attached at the raw ABI boundary and consumed at compile time.
- Delete the current public scalar `custom_primitive(...)` path instead of keeping two public protocols.

## Existing Code And Docs To Reuse

- `include/native_autodiff/native_autodiff.hpp`
- `include/native_autodiff/detail/callable_enzyme_impl.hpp`
- `include/native_autodiff/detail/custom_primitive_enzyme_impl.hpp`
- `tests/cpp/backend_dependency_consumer/main.cpp`
- `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`
- `tests/cpp/package_consumer/main.cpp`
- `documents/native-autodiff-runtime.md`
- `documents/native-autodiff-compiler-design.md`

Reuse constraints:
- Preserve base/enzyme target split in `CMakeLists.txt`.
- Preserve no-runtime-`__enzyme_autodiff` smoke.
- Preserve Kokkos same-code Serial/GPU smoke pattern.

## Implementation Source Packet

- required: `user_request_contract.md`
- required: this `design_brief.md`
- required: `test_plan.md`
- required: `documents/native-autodiff-runtime.md`
- required: `documents/native-autodiff-compiler-design.md`
- required: `include/native_autodiff/native_autodiff.hpp`
- required: `include/native_autodiff/detail/callable_enzyme_impl.hpp`
- required: `include/native_autodiff/detail/custom_primitive_enzyme_impl.hpp`
- required: `tests/cpp/backend_dependency_consumer/main.cpp`
- required: `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`
- required: `tests/cpp/package_consumer/main.cpp`
- required: `notes/worktrees/worktree_native_autodiff_linearization_2026-04-11.md`
- required: `notes/branches/native_autodiff_linearization_api.md`
- not used unless needed later: external references

## Patterns And Writing Style To Mirror

- Keep public contracts short and declaration-first in `native_autodiff.hpp`.
- Move heavy implementation into `include/native_autodiff/detail/*.hpp`.
- Use small comments only at boundary points that are otherwise hard to infer.
- Rewrite docs by replacing the old protocol, not by appending a second protocol.

## Reader Path And Term Introduction

- Reader should meet terms in this order:
  1. raw ABI primitive
  2. Kokkos adapter/wrapper
  3. Enzyme contract / derivative hook
  4. compile-time target/backend selection
- Avoid introducing scalar-expression custom primitive terminology before declaring it deleted.
- Make the key decision explicit near the top: the canonical primitive boundary is the raw function, not the wrapper and not an internal scalar IR node.

## Request Clause Mapping

- Satisfies `M1`, `M2`, `M3`, `M4`.
- Guards `N1`, `N2`, `N3`.
- Produces evidence for `E1`-`E5`.

## File-By-File Design

- `include/native_autodiff/native_autodiff.hpp`
  - Delete `CustomPrimitiveCall` and `custom_primitive(rule, operands...)`.
  - Introduce raw primitive contract declarations in the public header.
  - Keep declarations only; move heavy registration code to detail headers.
  - Keep callable autodiff on the existing flat scalar IR evaluator, and expose raw primitive autodiff as a separate canonical helper instead of adding a second callable custom-primitive protocol.
- `include/native_autodiff/detail/raw_primitive_enzyme_impl.hpp`
  - Implement raw-ABI registration helpers and Enzyme call sites.
  - Validate statically that hook signatures match the selected derivative mode.
- `include/native_autodiff/detail/callable_enzyme_impl.hpp`
  - Remove `CustomPrimitiveCall` handling from the flat evaluator.
  - Keep callable autodiff focused on ordinary scalar callable IR.
- `tests/cpp/backend_dependency_consumer/main.cpp`
  - Add canonical raw primitive example:
    - raw function body
    - `View` adapter
    - Kokkos Serial and DefaultExecutionSpace same-body smoke
- `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`
  - Delete scalar callable custom primitive coverage.
  - Keep low-level tensor IR coverage that is still in scope.
  - Replace custom derivative coverage with the new raw-ABI primitive helper path.
- `tests/cpp/package_consumer/main.cpp`
  - Replace installed-surface scalar custom primitive checks with raw primitive / Enzyme companion target checks.
- `documents/native-autodiff-runtime.md`, `documents/native-autodiff-compiler-design.md`
  - Rewrite the custom primitive section around raw ABI + Kokkos adapter + Enzyme boundary.
  - Remove statements that present scalar `custom_primitive(...)` as canonical.

## Design-To-Implementation Trace

- public contract replacement
  - clauses: `M1`, `M2`, `M3`
  - source/reuse: current `CustomPrimitiveSpec`, Kokkos backend consumer same-code smoke
  - tests: raw primitive derivative smoke, old scalar path deletion checks
  - evidence: `E1`, `E2`, `E3`, `E4`
- callable Enzyme path rewire
  - clauses: `M2`, `M3`
  - source/reuse: existing `CallableEnzymeAutodiffPath`, new `RawPrimitiveSpec` / `raw_gradient`
  - tests: smoke/package consumer/backend consumer, no-runtime-`__enzyme_autodiff`
  - evidence: `E1`, `E4`, `E5`
- docs rewrite
  - clauses: `M1`, `M2`, `M3`
  - tests: `make docs-check`
  - evidence: `E1`, `E2`, `E5`

## Identifier And Naming Plan

- Public contract should use `RawPrimitiveSpec`-style naming or a close variant that clearly marks the raw ABI boundary.
- Avoid keeping `custom_primitive(...)` as a public alias if the new protocol is installed in the same pass.
- `foo_raw` / `foo_from_view` style naming in tests/docs is acceptable because it directly mirrors the intended separation.

## Validation And Rollback Plan

- Validation:
  - root build/ctest
  - package install + consumer build/ctest
  - backend dependency consumer build/ctest
  - docs-check, agent-checks, pytest, ci-quick, diff-check
  - no-runtime-`__enzyme_autodiff` smoke retained
- Rollback:
  - no partial public fallback path
  - if raw ABI primitive path cannot fully replace the old scalar path in this pass, stop before deleting user-facing docs/claims and escalate instead of shipping dual protocols

## Risks

- Enzyme hook registration on raw ABI functions must stay compatible with Clang/Enzyme companion target packaging.
- raw primitive helper は current pass では one-or-two argument ABI に絞っているため、将来の shape/stride descriptor ABI では追加実装が必要になる。
- Kokkos wrappers must remain adapters only; accidentally attaching derivative policy there would reintroduce the wrong boundary.
