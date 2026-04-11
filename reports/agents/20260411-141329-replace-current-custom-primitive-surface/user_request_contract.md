# User Request Contract

- Run ID: 20260411-141329-replace-current-custom-primitive-surface
- Task: replace current custom primitive surface with raw ABI primitive contract integrated with Kokkos and Enzyme
- Owner: codex
- Created At (UTC): 2026-04-11T14:13:29Z

## Gate Status

- all_clauses_resolved: yes
- forbidden_drift_detected: no
- deferred_clause_ids:
- unresolved_clause_ids:

## Requirements Resolution Sweep

- `documents/native-autodiff-runtime.md`, `documents/native-autodiff-compiler-design.md`
- `notes/worktrees/worktree_native_autodiff_linearization_2026-04-11.md`, `notes/branches/native_autodiff_linearization_api.md`
- `notes/themes/USER_PREFERENCES.md`, `notes/guardrails/engineering_avoidances.md`
- `include/native_autodiff/native_autodiff.hpp`, `include/native_autodiff/detail/callable_enzyme_impl.hpp`, `include/native_autodiff/detail/custom_primitive_enzyme_impl.hpp`, `include/native_autodiff/kokkos_backend.hpp`
- `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`, `tests/cpp/package_consumer/main.cpp`, `tests/cpp/backend_dependency_consumer/main.cpp`
- `CMakeLists.txt`, `tests/cpp/backend_dependency_consumer/CMakeLists.txt`

## Resolved From Accumulated Context

| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |
| --------- | ------------- | ------------- | ---------- | -------------- |
| R1 | current_request + repo_or_code_precedent | `include/native_autodiff/detail/callable_enzyme_impl.hpp`, `include/native_autodiff/native_autodiff.hpp` | 現行 callable autodiff は元の C++ callable ではなく internal flat IR evaluator を Enzyme に渡しているため、raw ABI primitive を正本にするには callable autodiff 実行境界も組み替える必要がある | compile-time metadata と実行経路の責務分離を再設計する |
| R2 | current_request + durable_user_preference | `notes/themes/USER_PREFERENCES.md`, `documents/native-autodiff-runtime.md` | 中間の public stopgap を増やさず、現行 scalar `custom_primitive(...)` は撤去対象とする | diff が大きくなるので review/test を強く掛ける |
| R3 | repo_or_code_precedent | `tests/cpp/backend_dependency_consumer/main.cpp`, `documents/native-autodiff-runtime.md` | Kokkos は execution/runtime adapter に留め、raw ABI 本体は `View` wrapper の下で同じ code body を再利用する | raw primitive contract と Kokkos adapter の責務境界を docs に明示する |

## Must-Do Clauses

| Clause ID | Source Bucket | User Wording Or Evidence | Operational Interpretation | Owner Stage | Evidence Path | Status |
| --------- | ------------- | ------------------------- | -------------------------- | ----------- | ------------- | ------ |
| M1 | current_request | 「Kokkosも対応させるんだよ」「Raw側につけるんだよ」 | user-defined primitive の正式境界を raw ABI 関数側へ移し、Kokkos wrapper/view 側は薄い adapter にする | design/implementation | `include/native_autodiff/detail/raw_primitive_enzyme_impl.hpp`, `tests/cpp/backend_dependency_consumer/main.cpp`, `documents/native-autodiff-*` | resolved |
| M2 | current_request | 「ちょっとずつ作っても何も得るものはありません」「いったん全部消してもいいんじゃないですか？」 | 現行 scalar `CustomPrimitiveCall` / `custom_primitive(...)` path とその docs/tests を削除し、raw ABI contract へ置換する | implementation | `include/native_autodiff/native_autodiff.hpp`, `tests/cpp/*`, `documents/native-autodiff-*` | resolved |
| M3 | current_request | 「LLVMpassでmetadata注入->Enzyme->バイナリの順じゃない？」 | primitive metadata / derivative hook は raw ABI 境界で定義し、Enzyme compile-time path へ結ぶ。runtime に別 AD engine を残さない | design/implementation | `include/native_autodiff/detail/raw_primitive_enzyme_impl.hpp`, `tests/cpp/smoke/native_autodiff_ir_smoke.cpp`, `tests/cpp/package_consumer/main.cpp` | resolved |
| M4 | current_request | 「ウォーターフォール式に従って，サブエージェントも駆使して完成させてください」 | clause-driven design/test review を先に通し、read-only subagent review を入れてから implementation する | planning/review | `design_brief.md`, `test_plan.md`, subagent review notifications | resolved |

## Must-Not-Do Clauses

| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |
| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |
| N1 | current_request | scalar `custom_primitive(...)` と raw ABI primitive の二重 public protocol を残す | user が明示的に stopgap/parallel path を嫌っているため | implementation/review | API diff, docs diff, tests | clean |
| N2 | current_request | Kokkos wrapper 側に微分規則や primitive 契約を持たせる | primitive の正本が raw 側でなくなり、backend adapter と AD 境界が混線するため | design/review | docs, code review | clean |
| N3 | current_request | runtime で新しい AD engine や graph trace を持ち込む | user の compile-time Enzyme 境界要求と衝突するため | implementation/review | code review, symbol smoke | clean |

## Completion Evidence Clauses

| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |
| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |
| E1 | current_request | raw ABI primitive contract と derivative hook が code/docs/tests で正本化されている | `include/native_autodiff/*`, `documents/native-autodiff-*`, `tests/cpp/*` | verification | resolved |
| E2 | current_request | 旧 scalar `custom_primitive(...)` public path が code/docs/tests から消えている | same as above | verification | resolved |
| E3 | current_request | Kokkos view adapter が同じ raw code body を `Serial` と `DefaultExecutionSpace` で共有し、結果一致する | `tests/cpp/backend_dependency_consumer/main.cpp` | verification | resolved |
| E4 | current_request | Enzyme path は compile-time に消費され、final binary に runtime `__enzyme_autodiff` symbol を残さない | smoke/package consumer evidence | verification | resolved |
| E5 | repo_or_code_precedent | root/package/backend/docs/python/quick gates が通る | build/test logs and `verification.txt` | verification | resolved |

## Source Bucket Rules

- Allowed buckets: `current_request`, `durable_user_preference`, `repo_or_code_precedent`, `domain_or_external_constraint`, `unknown_or_open_question`.
- Durable user preferences do not become task requirements unless the current request or repo evidence supports the conversion.
- Unknowns stay unresolved, deferred, or escalated; they are not converted into silent assumptions.
- Active must-do, must-not-do, and completion-evidence clauses must not use `unknown_or_open_question`; unresolved items must move to Deferred Or Rejected Clauses after the resolution sweep.
- Do not stop at the first ambiguity if accumulated notes, repo docs, local code, tests, or prior logs can resolve it without changing user intent.

## Deferred Or Rejected Clauses

| Clause ID | Reason | Escalation Or Follow-Up Path | Status |
| --------- | ------ | ---------------------------- | ------ |

## Update Rule

- Every planning, design, implementation, and review artifact must cite the clause IDs it covers.
- If active work does not map to at least one must-do clause, stop and escalate instead of continuing.
- Closeout stays locked until every must-do and completion-evidence clause is resolved and every must-not-do clause remains clean.
