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

C / C++ 差分を build 境界、header 境界、所有権、例外・error path、test 追随の観点で厳密に確認します。

## Use When

- `cpp/src/`, `cpp/include/`, `cpp/tests/`, `cpp/experiments/` 配下を触る
- `cpp/CMakeLists.txt` や native build 設定を触る
- public header、ABI、FFI、CLI binary の挙動を変える
- C++ documentation / Docstring projection を触る
- `bootstrap_agent_run.py` の changed path 判定で `cpp_reviewer` が自動で足された

## Required Checks

- project-native configure / build / test evidence
- `ctest` があるならその結果
- CMake project なら `cmake -S "$ROOT/cpp" -B "$ROOT/build/cpp/<profile>" -DCMAKE_INSTALL_PREFIX="$ROOT/.state/cpp-install/<profile>"`、
  `cmake --build "$ROOT/build/cpp/<profile>" --parallel`、
  `ctest --test-dir "$ROOT/build/cpp/<profile>" --output-on-failure` の結果
- install contract がある場合は `cmake --install "$ROOT/build/cpp/<profile>"` の結果

## Core References

- `documents/conventions/coding-conventions-cpp.md`
- `documents/conventions/DOCSTRING_GUIDE.md`
- `documents/conventions/coding-conventions-testing.md`
- `documents/conventions/REVIEW_PROCESS.md`

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

## Expected Outcome

- public header、ABI、linkage、ownership、error path のリスクが明示されている
- 実行した build / test evidence と未実行の check が分かれている
- native 実装に追随すべき docs / build instructions / tests が確認されている

## Mandatory Checklist

- public header と implementation の整合を見ている
- lifetime、ownership、resource release、move/copy semantics の破綻を見ている
- bounds、null、error code、exception、failure path の扱いを見ている
- configure / build / test evidence が今回の差分に対して妥当か確認している
- build script、CMake、linkage、include path の影響を見ている
- native 実装に追随すべき docs や commands があれば確認している

## Default Sequence

1. changed native files、header、build files、関連 test files を固定します。
1. public header、ABI boundary、ownership boundary を先に確認します。
1. configure / build / test evidence を確認します。
1. findings を ABI and interface、memory and ownership、error path、test coverage、docs drift に分けて返します。

## Common Failure Modes

- header だけ変わって call site や docs が追随していない
- ownership、move/copy、resource cleanup の仮定が暗黙のまま壊れている
- `CMakeLists.txt` や link setting が変わったのに build evidence が薄い
- error path や malformed input の regression test が不足している
