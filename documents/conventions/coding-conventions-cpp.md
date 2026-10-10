<!--
@dependency-start
contract policy
responsibility Documents C++ コーディング規約 for this repository.
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
- C++ source path と configure graph は consumer が選択した profile に従います。
  profile の正本は [cpp-build-layout.md](../design/cpp-build-layout.md) です。
- `root-aggregate` profile は project root の既存 `CMakeLists.txt` を entrypoint とし、
  public headers と production source は project-owned `include/`、`src/` に置きます。
- `consumer-local` profile は選択された test/experiment manifest を個別に configure し、
  sibling consumer の graph を要求しません。
- `cpp/` prefix、root CMake の追加・削除、target 名を全 consumer 共通の規約にしません。

## 1.1 Native project boundary

| profile | graph owner | evidence command |
| --- | --- | --- |
| `root-aggregate` | project root CMake が production target と存在する consumers を登録する。target 名と test path は project-owned | consumer の root configure/build command |
| `consumer-local` | 選択された test/experiment manifest が一つの consumer graph を所有する | 当該 manifest の configure/build/test command |

Production target は consumer が選ぶ名前と interface を持ちます。Test と experiment
target も project-owned 名で production provider を consume し、target graph の configure
ownerだけが `add_subdirectory` または個別 configure route を決めます。AgentCanon runtime/template
test と cppdev の numerical/mathematical/NN oracle test は、それぞれの owning repository に
保持し、derived project の C++ test path へ複製しません。

## 禁止事項

- `root-aggregate` profile では `src/` が production translation unit、`include/` が public
  header の所有先です。Header-only/library artifact の選択は project の source/artifact
  contract へ残します。別 profile の source path はその project の layout owner が決めます。
- in-source build を禁止します。Binary directory は選択した CMake profile と project owner が決めます。

## 2. 命名規則

- 型は `UpperCamelCase`、関数と変数は `lower_snake_case` とします。
- 省略は最小限にし、意味が曖昧な略称は避けます。

## 3. 型と所有権

- 参照・ポインタの使い分けを明示し、所有権をコメントで説明します。
- `const` を適切に付け、意図しない変更を防ぎます。

## 3.5 Header-Only Rule

- template 既定では C++ 実装を持ちません。派生 repo で C++ を追加する場合、
  `root-aggregate` profile では `include/<project>/*.hpp` を既定にします。
- focused helper、policy class、FFI binding helper、shape/stride 変換、artifact loader helper は header-only にします。
- `root-aggregate` profile の `src/` に `.cc` / `.cpp` を置くのは、compile time、link time、ODR、
  外部 library 事情で header-only が不適切だと説明できる場合だけにします。
- `src/` を使うときは、なぜ header-only では駄目かを設計文書か change note に残します。

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

- 裸の数値リテラルは、[documents/conventions/common/01_principles.md](common/01_principles.md) のマジックナンバー規約に従います。
- `constexpr` / `inline constexpr` の名前付き定数、typed configuration、または public API 引数へ分離できる値は、式の途中に直接書きません。
- `-1`、`0`、`1`、`2`、`0.5` のような普遍的な符号・倍数以外を実装に置く場合は、`// NOLINT(readability-magic-numbers)` で数式や標準上の根拠を書きます。
- C++ project の source / header を変更した場合は、次を実行します。

```bash
run-clang-tidy.py -p <module-build-dir> <source>
```

`<module-build-dir>` は、project CMake preset または明示 configure command が選択した
実際の binary directory です。この引数は compile database の場所だけを指定し、runtime
backend を選びません。compile database の生成・更新は project build owner が行い、
この repository は active symlink や既定 compile database を作りません。native tool は
project の `.clang-tidy` を自動検出します。独自の config file を置く場合は native
`run-clang-tidy.py -config-file=<path>` 引数で明示してください。

AgentCanon 自体には C++ CMake project や compile database がないため、この repository
の編集だけを理由にそれらを生成しません。

## 5. テスト

- bounded かつ決定的な入力で検証します。
- 期待結果が分かるケース（対角行列、既知解など）を優先します。
- `jax.export` と C++ をつなぐ変更では、project-local smoke target を追加し、少なくとも
  `python3 tools/validation/ci/checks/check_jax_export_stack.py` と
  `cmake --build <selected-build-dir> --target <project-cpp-smoke-target>` を通します。

## 6. 再利用

- 再利用する local install tree は選択した project profile の install prefix に置きます。
- optional な local `jax.export` artifact は project-local `.state/<project>/jax-export/<profile>/` のように用途名を含む path に置きます。
- `docker/Dockerfile`、`pyproject.toml` の selected extras、project CMake entrypoint、optional
  `jax/jaxlib` version、calling convention が変わったら、必要な extras を選択した container
  boundary で project owner の configure command から rebuild します。
