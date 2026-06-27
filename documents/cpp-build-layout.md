<!--
@dependency-start
contract reference
responsibility Documents C++ Build Layout for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# C++ Build Layout

この template で C++ を使うときは、build layout を次で固定します。

## この文書の読み方

- この文書は、template-derived repo の C++ source/build directory と CMake
  entrypoint 配置を定めます。
- 主な順路は、Source Of Truth、Default Build Directories、Optional
  jax.export Flow、Reuse Policy、Recommended Profiles、Header-Only Default です。
- C++ 実装や build profile を追加する前に読みます。
- 境界: C++ algorithm-to-proof route は tool docs が扱い、この文書は build
  layout と配置を扱います。

## Source Of Truth

- root `CMakeLists.txt`
  - repo 全体の canonical CMake entrypoint
- `cmake/`
  - CMake helper module
- `include/`
  - public header。派生 repo が C++ を使う場合に追加する
- `src/`
  - header-only で収まらない特例実装だけ
- `lib/`
  - checked-in third-party source や補助 library
- `tests/cpp/`
  - smoke / test source

`CMakeLists.txt` を `src/` や `cpp/` の下へ分散させることを禁止します。entrypoint は root に 1 つだけ置きます。
template 既定では C++ 実装を持たず、root `CMakeLists.txt` は空の `INTERFACE` target だけを提供します。
派生 repo が C++ を使う場合は `include/<project>/*.hpp` から始め、`src/` を先に使う設計を標準にしません。

## Default Build Directories

- `build/cpp/<profile>/`
  - out-of-source build tree
- `.state/cpp-install/<profile>/`
  - local install tree

`build/` と `.state/` の内容は commit しません。人手で編集することも禁止します。

## Optional jax.export Flow

JAX / IREE / XLA FFI は template default ではありません。
必要な project だけ、Python export artifact、IREE runtime、C++ bridge、CMake module、smoke target を同じ change set で追加します。
C++ 側は同じ workspace の `include/` と root `CMakeLists.txt` から bridge を build し、`src/` は特例時だけ使います。

追加するときに候補になるものは次です。

- `jax.export`
  - StableHLO producer
- `iree-base-compiler`
  - StableHLO から VM flatbuffer を作る compiler
- `iree-base-runtime`
  - `local-task` CPU driver で compiled module を動かす runtime
- `jaxlib/include`
  - XLA FFI header

追加した project では、project-local smoke target を用意して次の形で通します。

```bash
python3 tools/ci/check_jax_export_stack.py
cmake -S . -B build/cpp/dev
cmake --build build/cpp/dev --target <project-cpp-smoke-target>
ctest --test-dir build/cpp/dev --output-on-failure
```

## Reuse Policy

`build/cpp/<profile>/`、`.state/cpp-install/<profile>/` は再利用してよいですが、次のどれかが変わったら rebuild します。

- `docker/Dockerfile`
- `docker/requirements.txt`
- root `CMakeLists.txt`
- `cmake/` 配下
- `src/`, `include/`, `lib/`, `tests/cpp/`
- optional JAX export を使う場合は `jax` / `jaxlib` version、calling convention、export する関数の signature、shape、dtype、platform

再利用は「同じ toolchain / 同じ ABI / 同じ export contract の範囲」に限定します。怪しい場合は cache を消して rebuild します。

## Recommended Profiles

- `build/cpp/dev`
  - 日常開発
- `build/cpp/docker-smoke`
  - Docker smoke
- `.state/cpp-install/dev`
  - local reusable install

## Header-Only Default

- canonical C++ target は空の `INTERFACE` library を既定にします。
- 派生 repo が C++ を使う場合だけ smoke / test binary を追加します。
- header-only で済むものを安易に `.cpp` へ分離しません。
