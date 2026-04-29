# cpp-review
<!--
@dependency-start
responsibility Documents cpp-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

C / C++ 差分を build 境界、header 境界、所有権、例外・error path、test 追随の観点で厳密に確認します。

## Use When

- `src/`, `include/`, `lib/` 配下を触る
- `CMakeLists.txt` や native build 設定を触る
- public header、ABI、FFI、CLI binary の挙動を変える
- `bootstrap_agent_run.py` の changed path 判定で `cpp_reviewer` が自動で足された

## Required Checks

- project-native configure / build / test evidence
- `ctest` があるならその結果
- CMake project なら `cmake -S . -B build` と `cmake --build build` の結果

## Core References

- `documents/coding-conventions-cpp.md`
- `documents/coding-conventions-testing.md`
- `documents/REVIEW_PROCESS.md`

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
