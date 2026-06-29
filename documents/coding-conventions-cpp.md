<!--
@dependency-start
contract policy
responsibility Documents C++ コーディング規約 for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
downstream design ./algorithm-implementation-boundary.md algorithm math-to-code boundary policy for C++ implementations
@dependency-end
-->

# C++ コーディング規約

この文書は、C++ で実装する場合の最低限の方針をまとめます。
現在の実装は主に Python ですが、将来の拡張に備えて記述しています。

layout と build tree の正本は [cpp-build-layout.md](cpp-build-layout.md) です。
数式、擬似コード、数値法、仕様境界を持つ C++ 実装では、実装前に [algorithm-implementation-boundary.md](algorithm-implementation-boundary.md) の Boundary Map を固定します。

## 1. 基本方針

- 明確で簡潔な実装を優先します。
- 例外や分岐が多くなる設計は避けます。
- 数値計算の安定性を意識し、前提条件をコメントで明示します。
- template 既定の C++ 実装形態は header-only にします。
- root `CMakeLists.txt` を canonical entrypoint にします。
- `cmake/` は helper module、`include/` は public header 兼 template 既定の実装置き場、`tests/cpp/` は test/smoke source に固定します。

## 禁止事項

- `src/` は header-only で収まらない特例実装だけに使います。新規 template 利用で最初から `src/` に実装を書くことを禁止します。
- in-source build を禁止します。`build/cpp/<profile>/` を使います。

## 2. 命名規則

- 型は `UpperCamelCase`、関数と変数は `lower_snake_case` とします。
- 省略は最小限にし、意味が曖昧な略称は避けます。

## 3. 型と所有権

- 参照・ポインタの使い分けを明示し、所有権をコメントで説明します。
- `const` を適切に付け、意図しない変更を防ぎます。

## 3.5 Header-Only Rule

- template 既定では C++ 実装を持ちません。派生 repo で C++ を追加する場合は `include/<project>/*.hpp` を既定にします。
- focused helper、policy class、FFI binding helper、shape/stride 変換、artifact loader helper は header-only にします。
- `src/` に `.cc` / `.cpp` を置くのは、compile time、link time、ODR、外部 library 事情で header-only が不適切だと説明できる場合だけにします。
- `src/` を使うときは、なぜ header-only では駄目かを設計文書か change note に残さなければなりません。

## 4. コメント

- 数式・アルゴリズムの前提を丁寧に書きます。
- 近似や数値安定性の注意点を必ず記述します。
- 実装 boundary が担う式、state、guard、alternate route を Boundary Map と一致させます。

## 4.5 数値リテラル

- 裸の数値リテラルは、`documents/conventions/common/01_principles.md` のマジックナンバー規約に従います。
- `constexpr` / `inline constexpr` の名前付き定数、typed configuration、または public API 引数へ分離できる値は、式の途中に直接書きません。
- `-1`、`0`、`1`、`2`、`0.5` のような普遍的な符号・倍数以外を実装に置く場合は、`// hardcoded-number-ok: <理由>` で数式や標準上の根拠を書きます。
- C++ source / header を変更した後は、次を実行します。

```bash
python3 tools/agent_tools/check_hardcoded_numbers.py \
  include src tests/cpp \
  --exclude vendor \
  --exclude reports
```

## 5. テスト

- bounded かつ決定的な入力で検証します。
- 期待結果が分かるケース（対角行列、既知解など）を優先します。
- `jax.export` と C++ をつなぐ変更では、project-local smoke target を追加し、少なくとも `python3 tools/ci/check_jax_export_stack.py` と `cmake --build build/cpp/<profile> --target <project-cpp-smoke-target>` を通します。

## 6. 再利用

- 再利用する local install tree は `.state/cpp-install/<profile>/` に置きます。
- optional な local `jax.export` artifact は project-local `.state/<project>/jax-export/<profile>/` のように用途名を含む path に置きます。
- `docker/Dockerfile`、`docker/requirements.txt`、`CMakeLists.txt`、`cmake/`、optional `jax/jaxlib` version、calling convention が変わったら rebuild します。
