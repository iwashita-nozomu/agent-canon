# cpp-review
<!--
@dependency-start
contract skill
responsibility Documents cpp-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ./catalog.yaml public skill and capability projection
upstream design ./skill-dependencies.yaml prerequisite and reviewer order
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json C++ validation profile owner
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse C++ projection
@dependency-end
-->


## Purpose

C / C++ 差分を build 境界、header 境界、所有権、例外・error path、test 追随の観点で
厳密に確認します。性能への影響または性能改善を主張する差分では、計測可能な workload と
metric を固定し、algorithm / data movement / memory hierarchy / concurrency / toolchain の
順に支配要因を確認します。小技、複雑な低レベル実装、compiler flag 自体を高速化の根拠に
しません。

## Use When

- `cpp/src/`, `cpp/include/`, `cpp/tests/`, `cpp/experiments/` 配下を触る
- `cpp/CMakeLists.txt` や native build 設定を触る
- public header、ABI、FFI、CLI binary の挙動を変える
- C++ documentation / Docstring projection を触る
- latency、throughput、memory footprint、allocation、scaling、起動時間、binary size、
  SIMD / vectorization、LTO / IPO / PGO、並列性能への影響または改善を主張する
- `bootstrap_agent_run.py` の changed path 判定で `cpp_reviewer` が自動で足された

## Required Checks

- project-native configure / build / test evidence
- When native static analysis is relevant and a CMake-generated database exists, use:
  `python3 tools/static_analysis/cpp/static_analysis.py select-db --workspace-root <workspace-root> --build-dir <build-dir>`;
  `python3 tools/static_analysis/cpp/static_analysis.py clangd-check --workspace-root <workspace-root> --source <source> --build-dir <build-dir>`;
  and `python3 tools/static_analysis/cpp/static_analysis.py clang-tidy --workspace-root <workspace-root> --source <source> --build-dir <build-dir>`.
  The build directory is explicit per module; the tool does not enumerate or add include paths,
  compiler flags, or provider-specific diagnostics.
- `ctest` があるならその結果
- CMake project なら `cmake -S "$ROOT/cpp" -B "$ROOT/build/cpp/<profile>" -DCMAKE_INSTALL_PREFIX="$ROOT/.state/cpp-install/<profile>"`、
  `cmake --build "$ROOT/build/cpp/<profile>" --parallel`、
  `ctest --test-dir "$ROOT/build/cpp/<profile>" --output-on-failure` の結果
- install contract がある場合は `cmake --install "$ROOT/build/cpp/<profile>"` の結果
- 性能変更が activation 条件を満たす場合は、repository-owned benchmark / profiler / workload
  route による before / after evidence。特定の benchmark framework、profiler、CPU counter、
  compiler、hardware を普遍要件にはしない

## Core References

- `documents/conventions/coding-conventions-cpp.md`
- `documents/conventions/DOCSTRING_GUIDE.md`
- `documents/conventions/coding-conventions-testing.md`
- `documents/conventions/REVIEW_PROCESS.md`

性能レビューの工学的参考資料として次の一次資料を使えます。これらは AgentCanon の第二
policy owner ではなく、この Skill の evidence contract を解釈するための reference です。

- [C++ Core Guidelines: Per — Performance](https://isocpp.org/guidelines)
- [Google Benchmark User Guide](https://google.github.io/benchmark/user_guide.html)
- [LLVM Auto-Vectorization diagnostics](https://llvm.org/docs/Vectorizers.html)
- [GCC Optimize Options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)
- [CMake CheckIPOSupported](https://cmake.org/cmake/help/latest/module/CheckIPOSupported.html)

## Target graph readback

- `cpp/CMakeLists.txt` が単一の native project entry として `cpp/src`、`cpp/include`、
  `cpp/tests`、`cpp/experiments` を同じ configure graph に接続します。
- `cpp-test-<name>` と `cpp-experiment-<name>` は `cpp-core` を consume し、
  `cpp-tests` と `cpp-experiments` は build grouping を提供します。
- root anchor、build tree、install prefix は `$ROOT/cpp`、`$ROOT/build/cpp/<profile>`、
  `$ROOT/.state/cpp-install/<profile>` に read back します。run/result publication は
  experiment lifecycle owner に残します。

## Docstring projection route

`agent_team.language_review_candidates` が native C/C++ implementation or test path（native suffix、
`cpp/CMakeLists.txt`、`cpp/src/`、`cpp/include/`、`cpp/tests/`、`cpp/experiments/`、
`cpp/cmake/` marker）を含む
changed surface に `cpp_reviewer` を候補として返した場合に、reviewer を起動します。
convention/template documentation は同じ
path inventory から `docs_workflow_steward` が担当し、catalog capability は OOP/type design
owner の選択に限ります。semantic clause の owner は `documents/conventions/DOCSTRING_GUIDE.md`
へ戻します。レビューは Doxygen syntax / format、header/source anchor、native ownership
evidence と、target responsibility region に選択した semantic delta が対応するかを確認
します。signature、namespace、field、型事実を comment に複製せず、`@param`、`@return`、
`@throws` の全 tag を意味契約の gate にしません。

Docstring または規約だけの差分では native build を追加せず、design/header/static evidence
で完了します。native source、header、ABI、または build configuration が変わった場合だけ
project-native configure / build / test route を起動します。

## Performance review activation boundary

性能 evidence を要求するのは、次のいずれかが今回の差分に存在するときです。

- PR、Issue、comment、API contract、test 名が性能改善または性能維持を主張する
- known critical path、hot loop、allocator / layout、I/O / transfer、threading / synchronization、
  compiler optimization setting を変える
- complexity、working-set size、copy / allocation count、host-device transfer、同期回数など、
 対象 workload の cost model を変える
- 既存の performance regression gate または benchmark contract が変更対象を覆う

単なる docs / comment、性能契約を持たない名前変更、非実行 metadata、または性能中立である
ことが構造的に明らかな差分へ benchmark を一律に追加しません。activation した場合も、
既存 repository-owned route を優先し、第二 benchmark framework、第二 profiler wrapper、
第二性能 score / threshold owner を追加しません。

実機または対象 runtime が利用できず性能主張を検証できない場合は、correctness evidence と
analytical cost change を性能実測の代用として合格扱いにしません。未検証の hardware、
workload、compiler、thread / device 条件を明記して handoff します。

## Performance review order

### 1. Contract、workload、metric

- latency、throughput、peak / steady-state memory、allocation count、startup、binary size、
  scalability のどれを改善または維持するのかを一つ以上明示します。
- representative input size、distribution、state、thread / process / device 数、warm / cold 条件、
  setup、I/O、transfer、synchronization を metric の対象に含めるかを固定します。
- profile、trace、call frequency、complexity、working-set estimate、既存 regression evidence の
  いずれかで critical path と仮説を支えます。測定なしの「一般に速い」は根拠になりません。
- 実装差分の semantic contract、ABI、numeric tolerance、determinism、resource limit を先に
  固定し、性能結果を得るために事後的に意味を変更しません。

### 2. Algorithm と不要処理

低レベルの命令置換より先に、workload 全体の支配項を確認します。

- asymptotic time / space complexity、iteration / pass 数、探索範囲、data structure、
  batching、I/O / syscall / transfer / synchronization 回数が適切か
- loop invariant、重複変換、重複 lookup、不要な format / parse、再計算、materialization を
  semantic contract の範囲で除けるか
- early exit、memoization、precomputation、fusion、parallelization が入力分布、memory 増加、
  invalidation、ordering、failure semantics と整合するか
- 局所 hotspot の高速化が end-to-end metric に寄与する割合を説明できるか

単純な高水準コードを、複雑な branchless trick、手動 unroll、custom allocator、intrinsic、
inline assembly へ置き換えるだけでは改善と判断しません。compiler、profile、benchmark の
根拠があり、保守コストと portability cost を上回る場合だけ採用候補にします。

### 3. Data movement、layout、allocation

- access pattern に対して contiguous / predictable traversal、working-set size、cache reuse、
  pointer chasing、strided / random access がどう変わるか
- AoS / SoA、index / pointer、compact representation、padding / alignment の選択が実際の
  field access と target architecture に対応するか。形だけで一律に優劣を決めない
- allocation / deallocation、container growth、temporary、deep copy、reference counting、
  serialization、host-device transfer の回数と byte 数を減らしているか
- `reserve`、buffer reuse、move、view、arena / pool 等が lifetime、invalidation、peak memory、
  exception safety、ownership を壊していないか
- object size や alignment の変更が ABI、cache footprint、vectorization、false sharing に
  与える影響を確認したか

copy を move に変える、reference を増やす、small object を heap 化する等を一般則として
適用しません。value category、lifetime、alias、escape、call frequency、object size の evidence
から判断します。

### 4. Branch、alias、vectorization、generated code

- branch predictability、dependency chain、alias、alignment、trip count、reduction、call boundary
  が compiler optimization を阻害または改善するという仮説を確認します。
- vectorization / inlining / unrolling の主張は、対象 compiler の optimization remarks、
  generated assembly、profile、performance counter のうち利用可能で最も直接的な evidence
  へ read back します。
- compiler が既に行う変換を手書きで複製せず、まず明確な loop/data dependency と型契約を
  提供します。
- code size、instruction cache、compile time、register pressure を無視した「より多く inline / 
  unroll / template 化」を推奨しません。

### 5. Concurrency と heterogeneous runtime

対象 runtime に並列性がある場合だけ次を確認します。

- lock contention、critical section、atomic traffic、cache-line ping-pong、false sharing、
  barrier / synchronization、queueing、task granularity、load balance、oversubscription
- thread 数、affinity、NUMA placement、process topology、device 数と対象 workload の対応
- CPU と accelerator 間の materialization、transfer、kernel launch、implicit synchronization、
  asynchronous lifetime の境界
- parallel speedup と同時に total work、memory footprint、tail latency、determinism、failure
  propagation が悪化していないか

memory order、locking、lifetime、stream / event dependency を速さのために暗黙に弱めません。
競合や順序を保証できない実装は、benchmark が速くても不合格です。

### 6. Toolchain optimization と numerical semantics

- optimized configuration で測定し、compiler / version、target architecture、標準 library、
  optimization flags、link mode を before / after で揃えます。
- LTO / IPO は target と toolchain の support を確認し、compile と link の双方を一貫させ、
  binary size、link time、debug / sanitizer / packaging への影響を含めて実測します。
- PGO は production を代表する profile workload、profile identity、generate / merge / use route、
  stale profile failure semantics を確認します。
- `-O3`、`-march=native`、fast-math、loop unroll、prefetch、SIMD intrinsic 等を無条件の tips として
 追加しません。target portability と実測効果を確認します。
- floating-point reassociation、NaN / Inf、signed zero、rounding、overflow、alias、alignment、
  object lifetime、undefined behavior に関する前提を暗黙に変更しません。精度、再現性、
  exception / error semantics の変更は独立した明示契約と test を必要とします。

## Benchmark evidence contract

性能を数値で主張するとき、review evidence は少なくとも次を read back します。

- **what**: metric、workload、input size / distribution、対象 path
- **where**: hardware / device、OS、compiler / version、standard library、build type / flags、
  thread / process / device topology
- **how**: timing scope、clock / counter、warm-up、iteration / repetition、setup / teardown、
  synchronization、CPU frequency / system load など支配的 noise の扱い
- **validity**: result が消去または constant-fold されていないこと、必要な output / state が
  observable なこと、correctness test と同じ semantic result を保つこと
- **result**: before / after の raw または repository-owned summary、sample count、median / mean 等の
  selected statistic、dispersion、実用上の差、regression threshold の根拠
- **scope**: 改善した条件、退化した条件、未検証の input / architecture / compiler、memory や
  tail latency 等の trade-off

benchmark setup を timing から外すことも含めることも一般則では決めません。対象 metric の
system boundary と一致させます。microbenchmark の改善を end-to-end 改善として外挿せず、
必要なら両方を分離して示します。noise より小さい差や単発の最良値を改善と断定しません。
固定の万能な改善率や統計手法は追加せず、既存 regression owner と観測ばらつきから判定します。

## Expected Outcome

- public header、ABI、linkage、ownership、error path のリスクが明示されている
- 実行した build / test evidence と未実行の check が分かれている
- native 実装に追随すべき docs / build instructions / tests が確認されている
- 性能変更では、critical path、cost hypothesis、before / after 条件、ばらつき、semantic risk、
  未検証範囲が分離されている
- speculative micro-optimization ではなく、測定された支配要因に対応する最小の
  contract-complete change が選ばれている

## Mandatory Checklist

- public header と implementation の整合を見ている
- lifetime、ownership、resource release、move/copy semantics の破綻を見ている
- bounds、null、error code、exception、failure path の扱いを見ている
- configure / build / test evidence が今回の差分に対して妥当か確認している
- build script、CMake、linkage、include path の影響を見ている
- native 実装に追随すべき docs や commands があれば確認している
- 性能 activation の有無を changed contract と主張から判定している
- activation した場合、metric / workload / critical path / cost hypothesis を固定している
- algorithm と data movement を低レベル instruction / flag より先に確認している
- memory access、allocation / copy、layout、並列 contention / synchronization の該当項目を
  evidence に基づいて確認している
- before / after の build、hardware、input、timing scope と統計が比較可能で、benchmark 自体が
  optimized away されていない
- performance change が correctness、defined behavior、ABI、numeric semantics、determinism、
  portability を暗黙に弱めていない
- benchmark / profiler / threshold / compiler policy の第二 owner を追加していない

## Default Sequence

1. changed native files、header、build files、関連 test files を固定します。
1. public header、ABI boundary、ownership boundary、semantic / numerical contract を先に確認します。
1. 性能 activation を判定し、activation した場合は workload、metric、critical path、cost hypothesis
   を固定します。
1. algorithm / total work、data movement / allocation、memory layout、concurrency、compiler-generated
   code の順で支配要因と差分機構を対応付けます。
1. configure / build / correctness test evidence を確認します。
1. activation した場合は comparable before / after benchmark / profile evidence と未検証条件を
   確認します。
1. findings を ABI and interface、memory and ownership、error path、correctness coverage、
   performance evidence、docs drift に分けて返します。

## Common Failure Modes

- header だけ変わって call site や docs が追随していない
- ownership、move/copy、resource cleanup の仮定が暗黙のまま壊れている
- `CMakeLists.txt` や link setting が変わったのに build evidence が薄い
- error path や malformed input の regression test が不足している
- profile や representative workload なしに局所コードを「高速」と断定する
- Debug と Release、異なる compiler flags / hardware / input を before / after として比較する
- warm-up、反復、ばらつき、setup / transfer / synchronization、dead-code elimination を扱わず
  単一 timing を採用する
- complexity、不要処理、data movement、allocation を残したまま branchless trick、manual unroll、
  intrinsic、custom allocator、LTO / PGO / fast-math を先に追加する
- microbenchmark の改善を end-to-end throughput / latency の改善として外挿する
- cache locality、working set、copy / temporary、false sharing、contention、oversubscription を
  説明せず並列化または layout 変更を行う
- performance のために memory order、bounds、lifetime、overflow、alias、floating-point、
  NaN / Inf、determinism の契約を暗黙に弱める
- repository-owned benchmark / validation route があるのに第二 framework、wrapper、threshold、
  score、CI gate を追加する
