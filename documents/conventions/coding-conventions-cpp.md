<!--
@dependency-start
contract policy
responsibility Documents C++ コーディング規約 for this repository.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse projection traces
downstream design ../design/algorithm-implementation-boundary.md algorithm math-to-code boundary policy for C++ implementations
@dependency-end
-->

# C++ コーディング規約

この文書は、C++ で実装する場合の最低限の方針をまとめます。
現在の実装は主に Python ですが、将来の拡張に備えて記述しています。

layout と build tree の正本は [cpp-build-layout.md](../design/cpp-build-layout.md) です。
数式、擬似コード、数値法、仕様境界を持つ C++ 実装では、実装前に [algorithm-implementation-boundary.md](../design/algorithm-implementation-boundary.md) の Boundary Map を固定します。

## 1. 基本方針

- 明確で簡潔な実装を優先します。
- 例外や分岐が多くなる設計は避けます。
- 数値計算の安定性を意識し、前提条件をコメントで明示します。
- template 既定の C++ 実装形態は header-only にします。
- `cpp/CMakeLists.txt` を唯一の C++ project entrypoint にします。
- `cpp/cmake/` は project-local helper module、`cpp/include/` は public header、
  `cpp/src/` は production implementation、`cpp/tests/` は CTest source、
  `cpp/experiments/` は native experiment source と target wiring に固定します。
- parent root は language-neutral な入口として保ち、C++ command は `cpp` を
  source anchor にして実行します。

## 1.1 Native project boundary

| owner | path/state | evidence command |
| --- | --- | --- |
| project | `cpp/CMakeLists.txt` が `cpp/src`、`cpp/include`、`cpp/tests`、`cpp/experiments` を同一 configure graph に登録する | `cmake -S "$ROOT/cpp" -B "$ROOT/build/cpp/<profile>"` |
| production | `cpp-core` が public header と production source を提供する | `cmake --build "$ROOT/build/cpp/<profile>" --target cpp-core` |
| tests | `cpp-test-<name>` が `cpp-core` を consume し、CTest が実行を所有する | `cmake --build "$ROOT/build/cpp/<profile>" --target cpp-tests`; `ctest --test-dir "$ROOT/build/cpp/<profile>"` |
| experiments | `cpp-experiment-<name>` が `cpp-core` を consume し、build と run を分離する | `cmake --build "$ROOT/build/cpp/<profile>" --target cpp-experiments` |

## 禁止事項

- `cpp/src/` は production translation unit の所有先です。header-only の `cpp-core` は
  `cpp/include/` を中心に構成し、translation unit と artifact の選択は source/artifact
  contract として設計記録へ残します。
- in-source build を禁止します。`build/cpp/<profile>/` を使います。

## 2. 命名規則

- 型は `UpperCamelCase`、関数と変数は `lower_snake_case` とします。
- 省略は最小限にし、意味が曖昧な略称は避けます。

## 3. 型と所有権

- 参照・ポインタの使い分けを明示し、所有権をコメントで説明します。
- `const` を適切に付け、意図しない変更を防ぎます。

## 3.5 Header-Only Rule

- template 既定では C++ 実装を持ちません。派生 repo で C++ を追加する場合は `cpp/include/<project>/*.hpp` を既定にします。
- focused helper、policy class、FFI binding helper、shape/stride 変換、artifact loader helper は header-only にします。
- `cpp/src/` に `.cc` / `.cpp` を置くのは、compile time、link time、ODR、外部 library 事情で header-only が不適切だと説明できる場合だけにします。
- `cpp/src/` を使うときは、なぜ header-only では駄目かを設計文書か change note に残さなければなりません。

## 4. コメント

- 数式・アルゴリズムの前提を丁寧に書きます。
- 近似や数値安定性の注意点を必ず記述します。
- 実装 boundary が担う式、state、guard、alternate route を Boundary Map と一致させます。

### Docstring / native documentation projection

意味契約と canonical skeleton は [DOCSTRING_GUIDE.md](./DOCSTRING_GUIDE.md) が所有し、この
文書は C++ adapter として Doxygen-compatible comment、宣言 / header placement、native
ownership boundary の syntax と format を選びます。責務の一文に、reviewer matrix が選んだ
algorithm、failure、side effect、ownership の semantic delta だけを加えます。

signature、namespace、access modifier、field、型事実の列挙は comment に複製しません。
`@param`、`@return`、`@throws` などの tag は読者の判断に必要な relation がある場合だけ
使い、全宣言に固定しません。target identity と header/source anchor は
[cpp-build-layout.md](../design/cpp-build-layout.md) へ戻し、Docstring projection はその
design fact を再定義しません。

## 4.5 数値リテラル

- 裸の数値リテラルは、`documents/conventions/common/01_principles.md` のマジックナンバー規約に従います。
- `constexpr` / `inline constexpr` の名前付き定数、typed configuration、または public API 引数へ分離できる値は、式の途中に直接書きません。
- `-1`、`0`、`1`、`2`、`0.5` のような普遍的な符号・倍数以外を実装に置く場合は、`// hardcoded-number-ok: <理由>` で数式や標準上の根拠を書きます。
- C++ source / header を変更した後は、次を実行します。

```bash
python3 tools/agent_tools/check_hardcoded_numbers.py \
  cpp/include cpp/src cpp/tests cpp/experiments \
  --exclude vendor \
  --exclude reports
```

## 5. テスト

- bounded かつ決定的な入力で検証します。
- 期待結果が分かるケース（対角行列、既知解など）を優先します。
- `jax.export` と C++ をつなぐ変更では、project-local smoke target を追加し、少なくとも `python3 tools/ci/check_jax_export_stack.py` と `cmake --build "$ROOT/build/cpp/<profile>" --target <project-cpp-smoke-target>` を通します。

## 6. 再利用

- 再利用する local install tree は `.state/cpp-install/<profile>/` に置きます。
- optional な local `jax.export` artifact は project-local `.state/<project>/jax-export/<profile>/` のように用途名を含む path に置きます。
- `docker/Dockerfile`、`docker/requirements.txt`、`cpp/CMakeLists.txt`、`cpp/cmake/`、optional `jax/jaxlib` version、calling convention が変わったら `cmake -S "$ROOT/cpp" -B "$ROOT/build/cpp/<profile>"` から rebuild します。
