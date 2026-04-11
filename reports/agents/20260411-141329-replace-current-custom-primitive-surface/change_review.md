# Change Review

- Run ID: 20260411-141329-replace-current-custom-primitive-surface
- Task: replace current custom primitive surface with raw ABI primitive contract integrated with Kokkos and Enzyme
- Owner: codex

## Chunk Findings

| Chunk | Finding | Severity | Status |
| ----- | ------- | -------- | ------ |
| raw primitive helper | `raw_gradient` の Enzyme call site が tuple/lambda flatten で壊れていた | high | fixed |
| package consumer | legacy `ConsumerInlineGradientFunction` 参照が残っていた | high | fixed |
| docs | scalar `custom_primitive(...)` を canonical path と書く drift が残っていた | high | fixed |
| backend consumer | Kokkos same-code smoke が `foo_raw` / `foo_from_view` 形になっていなかった | medium | fixed |

## Reuse And Style Findings

- public contract は `native_autodiff.hpp` 側に declaration-first で残し、重い raw primitive wiring は `detail/raw_primitive_enzyme_impl.hpp` に分離した。
- callable autodiff の既存 value/Enzyme split は維持し、user-facing custom derivative protocol だけ raw ABI helper に切り出した。
- Kokkos consumer は既存 same-code smoke を raw ABI wrapper へ言い換える最小差分で更新した。

## Design-Base Implementation Review

- `M1`: `RawPrimitiveSpec<&foo_raw<double>>` と `raw_gradient` を追加し、backend consumer を `sum_raw` / `sum_from_view` 形へ更新した。
- `M2`: scalar `CustomPrimitiveCall` / `custom_primitive(...)` public path を header/tests/docs から除去した。
- `M3`: raw ABI hook registration は generated wrapper 経由で Enzyme compile-time path に接続し、runtime `__enzyme_autodiff` symbol 不在 smoke を維持した。
- `M4`: implementation 前に design/test review subagent を回し、blocking findings を反映した。

## Remaining Work Review

- planned work unit は code/docs/tests/backend/package/validation まで完了。
- closeout artifact の commit/push 反映だけが残りで、実装チャンクの revise は残していない。

## User Request Trace Review

- diff は raw ABI primitive 正本化、Kokkos adapter-only、Enzyme compile-time-only の user request に沿っている。
- wrapper 側へ derivative policy を置かず、scalar stopgap public path を復活させていない。

## Revision Loop

- なし。fix-now findings は実装に反映済み。

## Follow-Up

- 将来拡張として raw helper の arity 3 以上や shape/stride descriptor ABI は別 pass で扱う。
