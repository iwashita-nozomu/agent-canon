# Test Plan

- Run ID: 20260411-141329-replace-current-custom-primitive-surface
- Task: replace current custom primitive surface with raw ABI primitive contract integrated with Kokkos and Enzyme
- Owner: codex

## Static Path Survey

- callable Enzyme execution wrapper vs metadata-only IR path
- current scalar custom primitive declarations and detail helpers
- backend dependency consumer Kokkos same-code Serial/GPU smoke
- installed package base/enzyme target split
- no-runtime-`__enzyme_autodiff` symbol smoke

## Nasty Cases

| Target | Case | Why It Is Nasty | Expected Outcome | Status |
| ------ | ---- | --------------- | ---------------- | ------ |
| raw primitive execution | same raw code body via `Kokkos::Serial` and `Kokkos::DefaultExecutionSpace` | proves wrapper is adapter-only and execution parity holds across backends | identical numeric result on both execution spaces | passed |
| raw primitive autodiff | raw primitive without explicit hook | proves Enzyme/default path still works after scalar custom primitive removal | analytic baseline matches | passed |
| raw primitive autodiff | explicit custom gradient hook with intentionally non-analytic values | proves user-defined derivative hook wiring is active rather than analytic fallback | shadow buffer uses hook-defined values | passed |
| raw primitive autodiff | augmented reverse hook | proves custom tape/reverse path works on the raw ABI boundary | shadow buffer uses augmented-hook values | passed |
| packaging/runtime boundary | final binaries should not retain `__enzyme_autodiff` | proves Enzyme is compile-time only | symbol absent from root/package binaries | passed |
| protocol deletion | old scalar `ad::custom_primitive(...)` callable path | ensures dual protocol does not silently survive | code/docs/tests no longer expose the legacy public path | passed |

## Regression Cases To Keep

- base target without Enzyme remains usable for value/metadata-only consumers
- existing low-level tensor IR smoke that is still in scope must remain until raw ABI path fully replaces only the custom primitive surface
- root/package/backend/doc/agent/pytest/quick gates remain the fixed regression wall

## Implementation Notes

- root smoke carries default/custom/augmented raw primitive derivative evidence
- installed package consumer uses the same raw primitive helper path
- backend consumer carries the canonical `foo_raw(ptr, n)` + `foo_from_view(view)` Kokkos adapter smoke
- validation evidence stays in the same pass: root CTest, package consumer, backend consumer, docs-check, agent-checks, pytest, ci-quick, diff-check
