# C++ Review

## Scope

- Files reviewed:
  - `include/native_autodiff/native_autodiff.hpp`
  - `include/native_autodiff/detail/raw_primitive_enzyme_impl.hpp`
  - `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`
  - `tests/cpp/package_consumer/main.cpp`
  - `tests/cpp/backend_dependency_consumer/main.cpp`
- Public headers or ABI surfaces touched:
  - `RawPrimitiveSpec<&foo_raw<double>>`
  - `raw_const`, `raw_dup`, `raw_gradient`
- Build or test entrypoints checked:
  - `native_autodiff_smoke`
  - installed package consumer
  - backend dependency consumer

## Findings

### Fix Now

- `raw_gradient` の Enzyme call site は tuple/lambda flatten では通らず、direct raw ABI call + generated hook wrapper に修正した。
- custom hook の ABI は scalar metadata shadow slot を含む実際の Enzyme signature に合わせて修正した。
- stale package consumer の legacy inline-gradient path は削除した。

### Follow-Up

- raw helper の arity 3 以上や richer descriptor ABI は別 pass で拡張する。

### Delete-Ok

- legacy scalar `CustomPrimitiveCall` / `custom_primitive(...)` public path
- `ConsumerInlineGradientFunction` legacy test path

## Native Code Checklist

- ownership / lifetime / aliasing risks checked: yes, raw helper is explicit pointer/shadow API only
- header / implementation consistency checked: yes
- boundary and error-path coverage checked: yes, raw hook signature validation added
- build / configure / test evidence checked: yes
- docs or developer-command follow-through checked: yes

## Notes

- raw primitive contract is now the only user-facing custom derivative path; tensor custom-elementwise remains backend-facing compatibility only.
