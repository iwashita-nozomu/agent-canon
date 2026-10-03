# cpp-review
<!--
@dependency-start
contract skill
responsibility Reviews selected C/C++ contract, build, ownership, and performance risks with point-of-use validation.
upstream design ../canonical/skills.md skill canon registry
upstream design ./catalog.yaml public skill and capability projection
upstream design ./skill-dependencies.yaml prerequisite and reviewer order
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json C++ validation profile owner
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse C++ projection
upstream design ../../documents/design/cpp-debugging.md native debugging selection and evidence boundary
@dependency-end
-->

## Reader Map

Select the changed contract before reading checks. A language-review candidate is
not a reviewer activation; the selected owner must need a concrete C/C++ claim or
risk resolved. Reuse an active reviewer when it already owns that claim.

| Current change or decision | Read next |
| --- | --- |
| Native source, public header, ABI, or build configuration | [Required Checks](#required-checks) and the relevant interface/ownership evidence |
| Docstring or convention prose only | [Docstring projection route](#docstring-projection-route); no native build is added |
| CMake clangd/LSP analysis setup | [CMake analysis environment](#cmake-analysis-environment) |
| Crash, hang, lifetime, initialization, or race diagnosis | [Runtime debugging](#runtime-debugging) |
| Performance claim or changed workload cost | [Performance review activation boundary](#performance-review-activation-boundary), then its selected performance section |
| Execute any selected program/check | [Project-owned execution](#project-owned-execution) |

Read later debugging, benchmark, and recovery details when their condition is true.
A documentation-only task with no performance claim uses documentation evidence;
seeing this Skill or a C++ path does not activate every row.

## Purpose

Review C/C++ changes for build/header boundaries, ABI, ownership, lifetime,
exceptions/error paths, and required test/documentation follow-through. For a selected
performance change, establish workload and metric, then investigate algorithm,
data movement, memory hierarchy, concurrency, and toolchain in that order.
Complex low-level code or a compiler flag alone is not performance evidence.

## Use When

Use when an active review requires native C/C++ evidence, including changes beneath
`cpp/src/`, `cpp/include/`, `tests/cpp/`, `cpp/experiments/`, native build settings,
public headers, ABI/FFI/CLI behavior, or C++ Docstring projection. CMake analysis
setup and explicit native performance/debugging requests use their matching rows.
A `cpp_reviewer` candidate from changed-path routing is considered under the same
claim/risk condition rather than automatically launched.

## Project-owned execution

通常の configure / build / test / static analysis は、project-owned の規定経路を
既定設定のまま実行します。`make run tests/cpp/nn` が入口なら、その command を先に
実行し、失敗した場合だけ必要な経路診断を行います。Docker context / image、cgroup
version / driver、有限の memory / CPU / PIDs 上限の事前確認は行わず、未設定・
未確認や cgroup v1 を理由に開始を止めません。

資源上限が必要なら、consumer の Compose 等の既存実行設定へ宣言し、並列度も既存の
build 設定に置きます。設定と適用はその owner の責務であり、AgentCanon の request
JSON、host lease、別ランナーで重ねません。上限設定の追加を通常実行の前提にしません。

規定経路の権限・終了コードと明示された再実行禁止を維持し、別 daemon や host 直実行へ
迂回しません。再実行禁止は縮小 build・別 target・小規模 GPU にも適用し、既存 evidence と
fixture-only 検証へ限定します。禁止を解く根拠に過去の別許可を使いません。
Failed verification follows [the topic-record owner](../../documents/operations/notes-lifecycle.md#failed-verification-record)
with the actual command, observed result, affected property, and next owner/action.

## CMake analysis environment

CMake project の clangd / LSP 解析を準備するときは、既存の project-owned configure
argv に `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` を加え、build directory に
`compile_commands.json` を生成します。既存 configure preset の同等の cache 設定も
使えます。source / build directory、toolchain、backend、依存解決は実ビルドと揃え、
同じ構成の最新 DB が既にあれば再生成しません。compiler を起動する configure も
project-owned の規定経路で行います。この生成機能は Ninja / Makefile 系が対象で、
非対応 generator を勝手に切り替えず、生成できない範囲を未検証として残します。

clangd は依存を持つ既存の開発コンテナなど、実ビルドの環境で動かし、対象 module の
build directory を `--compile-commands-dir=<build-dir>` で指定します。DB は compiler
argv の記録であり、依存を取得・同梱しません。参照する source、依存ヘッダー、標準
ライブラリ、toolchain がその環境から読める必要があります。生成ヘッダーが必要なら
既存の生成 target までを準備し、解析準備だけを理由に full build / test を要求しません。
include path、define、言語規格を Neovim 側で手書きして第二の設定にしません。

開いている workspace 内で依存を実際に include する translation unit を選び、下記の
既存 `clangd-check` 経路で DB と compile command の読込み・依存解決・診断を確認します。
DB 生成成功と依存込み解析成功を分け、結果と未検証範囲を Issue / PR に残します。
ホストの Neovim とコンテナの workspace path 対応は必要ですが、コンテナ専用の外部
ヘッダー自体をホストで開くための複製・転送は、この workspace 内解析の終了条件にしません。
通常の docs-only 編集へ configure / build / LSP 実行を一律に追加しません。

根拠は [CMake compilation database](https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html)
と [clangd compile commands](https://clangd.llvm.org/design/compile-commands) です。

## Required Checks

This section applies to changed native source/header/ABI/build contracts. A Docstring
or convention-only change goes directly to its projection section. Select the
project-native configure/build/test evidence that covers the changed contract;
consume combined runner results without duplicating each underlying command.
Use configured `ctest` and installation evidence when those contracts are affected.

When static analysis is relevant and a CMake-generated database exists, use the
existing `tools/validation/code/static/cpp/static_analysis.py` operations `select-db`,
`clangd-check`, and `clang-tidy` with explicit `--workspace-root`, module `--build-dir`,
and the selected `--source` where required. Execute through the existing owner route.
Do not enumerate extra include paths, compiler flags, or provider-specific diagnostics.

Trace public header/implementation and call-site correspondence, linkage/ABI,
lifetime, ownership, move/copy, resource release, bounds, null, exception/error
behavior, and affected tests/docs. Inspect the changed mechanism and reachable
failure paths rather than freezing private helper layout. Preserve required inputs,
safety, numerical semantics, and existing regression contracts.

Only a performance-activated change requires its comparable benchmark/profiler
results. Do not require a universal profiler, hardware counter, compiler, benchmark
framework, or new threshold owner.

## Runtime debugging

For crash, hang, lifetime violation, uninitialized values, data races, or an explicit
debugging request, read [C++ debugging](../../documents/design/cpp-debugging.md) and
select needed GDB, Valgrind Memcheck, or existing compiler sanitizer evidence.
Keep the project-owned runner, permissions, resource and rerun limits. Diagnostic
command success and program success are separate observations; preserve stacks,
diagnostics, and the unverified scope in the existing Issue/PR.

## Core References

- [C++ conventions](../../documents/conventions/coding-conventions-cpp.md)
- [Docstring contract](../../documents/conventions/DOCSTRING_GUIDE.md)
- [Testing conventions](../../documents/conventions/coding-conventions-testing.md)
- [Review process](../../documents/conventions/REVIEW_PROCESS.md)

Performance references support the selected engineering judgment; they are not
additional policy owners or a startup reading list:

- [C++ Core Guidelines](https://isocpp.org/guidelines)
- [Google Benchmark](https://google.github.io/benchmark/user_guide.html)
- [LLVM vectorization diagnostics](https://llvm.org/docs/Vectorizers.html)
- [GCC optimization options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)
- [CMake IPO support](https://cmake.org/cmake/help/latest/module/CheckIPOSupported.html)

## Target graph readback

For the selected `cpp/CMakeLists.txt` project graph, read back its existing contract:
`cpp/src`, `cpp/include`, `${ROOT}/tests/cpp`, and `cpp/experiments` share the configure
graph; tests use explicit out-of-tree source/binary directories. `cpp-test-<name>` and
`cpp-experiment-<name>` consume `cpp-core`, with `cpp-tests` / `cpp-experiments` grouping.
The anchors are `$ROOT/cpp`, `$ROOT/build/cpp/<profile>`, and
`$ROOT/.state/cpp-install/<profile>`. Run/result publication stays with experiment
lifecycle. These project-specific paths do not replace another consumer's graph.

## Docstring projection route

For a selected C/C++ semantic-documentation review, use
[DOCSTRING_GUIDE](../../documents/conventions/DOCSTRING_GUIDE.md) as clause owner.
A native suffix or `cpp_reviewer` candidate alone does not require a new reviewer;
activate only a needed native claim/risk. Convention/template prose belongs to the
selected documentation owner. OOP/type-design capability selection stays separate.

Review Doxygen syntax/format, header/source anchors, native ownership evidence, and
correspondence to the selected semantic delta. Do not copy signatures, namespace,
fields, or type facts into comments or require every `@param`/`@return`/`@throws` tag.
Docstring or convention-only changes close with design/header/static evidence.
Changed source/header/ABI/build behavior uses the Required Checks route above.

## Performance review activation boundary

Activate performance review when the change claims improved or preserved performance;
changes a known critical path, hot loop, allocation/layout, I/O/transfer,
threading/synchronization or compiler optimization; changes the workload cost model
(complexity, working set, copies, transfers, synchronization); or falls under an
existing performance regression contract.

A performance-neutral rename, non-executable metadata, or ordinary comment/docs
change without a performance claim does not require benchmarking. When active,
use the repository-owned workload, profiler and benchmark. Keep correctness and
analytical cost evidence distinct from empirical performance. If the required
runtime is unavailable, report exact hardware/workload/compiler/thread/device gaps;
do not mark an unmeasured improvement verified.

## Performance review order

Select the relevant subsections only after the activation decision above.

### Numerical solver handoff boundary

For C/C++ numerical solvers or iterative algorithms, first read
[computational-optimization](computational-optimization.md) for convergence-first
numerical performance diagnosis. Its post-run classification uses
`tools/analysis/numerical/numeric_performance.py --input <post-run-observations.json>
--format json` through the existing route. The dependency dictionary exposes a
conditional candidate, not a mandatory prerequisite for all C++ reviews.

Changed iterations, residual/objective/KKT trajectory, finite state, accepted steps,
termination, conditioning, inner-solver work, or objective/gradient/evaluation/
linear-solve/matvec counts return to the mathematical/algorithm owner. Systems/JIT
handoff requires unchanged numerical trajectory, work counters, problem, initial
state, stopping policy, dtype, workload, run mode, cache, backend, device and compiler,
with a positive regression in the relevant compile/JIT, iteration, evaluation,
linear-solve, transfer/synchronization or total component.

Different comparison context or missing finite/non-finite events is
`evidence_missing`, not systems attribution. Total-only or unattributed total growth
is `evidence_missing` / `unattributed_total`; obtain relevant component evidence
before proposing a JIT-boundary change. Non-solver performance uses the native
workload/data-movement route without a convergence-record requirement.

### 1. Contract、workload、metric

Fix latency, throughput, memory, allocation, startup, binary size or scaling metrics
and representative input size/distribution/state, concurrency/device counts,
warm/cold conditions, and setup/I/O/transfer/synchronization measurement boundaries.
Support a critical-path hypothesis with profile, trace, call frequency, complexity,
working-set estimate or existing regression evidence. Preserve semantic/ABI/numeric
and resource guarantees instead of changing them after seeing results.

### 2. Algorithm と不要処理

Start with total asymptotic work/space, iterations/passes, search, data structures,
batching and I/O/syscall/transfer/synchronization counts. Check redundant conversions,
lookups, format/parse, recalculation and materialization against loop invariants.
Early exit, caching, precomputation, fusion and parallelization must preserve input,
memory, invalidation, order and failure contracts. Explain the hotspot's contribution
to the end-to-end metric. Branchless tricks, unrolling, allocators, intrinsics and
assembly require compiler/profile/benchmark evidence and justified maintenance and
portability cost, not speculative speed claims.

### 3. Data movement、layout、allocation

Relate access patterns, contiguous traversal, working sets, cache reuse, pointer
chasing, strides and randomness to actual fields and architecture. Check AoS/SoA,
indices/pointers, compact representation, padding/alignment, allocation/growth,
temporaries, deep copies, refcounts, serialization and host-device byte/count changes.
`reserve`, buffer reuse, moves, views and arenas must preserve lifetime, invalidation,
peak memory, exceptions and ownership. Evaluate ABI/cache/vectorization/false-sharing
impacts. Neither moves nor references nor heap allocation is a universal improvement;
use value category, alias/escape, frequency, lifetime and size evidence.

### 4. Branch、alias、vectorization、generated code

Check branch prediction, dependency chains, aliases, alignment, trip counts,
reductions and call boundaries. Support vectorization/inlining/unrolling claims with
compiler remarks, assembly, profiles or relevant counters. Expose clear data and type
dependencies rather than copying compiler transformations. Include code size,
instruction cache, compile time and register-pressure costs.

### 5. Concurrency と heterogeneous runtime

When parallel execution is involved, inspect contention, atomics/cache-line traffic,
false sharing, barriers, queueing, task size, load balance and oversubscription.
Relate affinity/NUMA/process/device topology to workload, and trace materialization,
transfers, launches, implicit synchronization and asynchronous lifetime. Compare
total work, memory, tail latency, determinism and failure propagation as well as
speedup. Preserve memory order, locking, lifetimes, stream/event dependencies and
race freedom even when a weaker implementation benchmarks faster.

### 6. Toolchain optimization と numerical semantics

Compare optimized builds with matched compiler/version, architecture, standard
library, flags and link mode. LTO/IPO needs compile/link support and evidence about
size, link time, debugging, sanitizers and packaging. PGO needs representative training
workload, profile identity and generation/merge/use/staleness semantics. Flags such as
`-O3`, `-march=native`, fast-math, prefetch and SIMD need portability and measured
benefit. Preserve floating-point reassociation, NaN/Inf, signed zero, rounding,
overflow, alias/alignment, lifetime and defined-behavior assumptions. Numerical
accuracy/reproducibility/exception changes require their own explicit contract/tests.

## Benchmark evidence contract

For empirical performance claims, retain what (metric/workload/input/path), where
(hardware/OS/compiler/library/flags/topology), how (timing/clock/counter/warm-up/
repetitions/setup/synchronization/noise), validity (observable output, no dead-code
or constant-folded result, same semantic result), result (before/after raw or owned
summary, sample count, selected statistics, dispersion, meaningful effect and
regression-threshold rationale), and scope (regressions, untested conditions,
memory/tail-latency trade-offs).

Timing boundaries follow the metric. Do not extrapolate a microbenchmark to
end-to-end behavior, use a single best timing as proof, or call a below-noise effect
an improvement. Use existing regression ownership and observed variation rather
than adding a universal improvement percentage or statistical method.

## Expected Outcome

Report selected interface/ownership/error/correctness/build/docs findings and actual
validation with its unrun scope. Performance findings retain the cost hypothesis,
comparison conditions, variability, semantic risks and unverified conditions. Choose
the smallest contract-complete correction supported by the observed dominant cause.

## Mandatory Checklist

Apply the current Reader Map row and shared safety/semantic constraints. Native
review uses Required Checks, documentation review its projection, and performance
review its activation and selected evidence sections. This heading does not create
a second unconditional build or benchmark checklist.

## Default Sequence

Select the changed contract and required risk, read its current section, obtain
owner-defined evidence, and report findings with limits. Resolve additional runtime,
performance or numerical questions at the conditional routes above, then return to
the same review. Reuse valid existing results rather than rerunning a whole sequence.

## Common Failure Modes

Watch for unmigrated callers/docs after a header change, implicit lifetime/ownership
assumptions, build changes without selected build evidence, and untested reachable
error paths. Under performance activation, reject unmatched build/hardware/input
comparisons, missing warm-up/repetition/noise or dead-code controls, low-level tricks
before algorithm/data-movement analysis, unexplained concurrency/layout changes,
weakened numerical or memory semantics, and duplicate benchmark/profiler frameworks.
