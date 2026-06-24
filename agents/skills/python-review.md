# python-review
<!--
@dependency-start
contract skill
responsibility Documents python-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

Python 差分を型、テスト、lint、境界設計の観点で厳密に確認します。

## Use When

- `python/` 配下を触る
- pyright warning を扱う
- API や型境界を変える
- `bootstrap_agent_run.py` の changed path 判定で `python_reviewer` が自動で足された

## Required Checks

- `pyright`
- `pytest tests/`
- `ruff check python tests --select D,E,F,I,UP --ignore E501`
- `python3 tools/oop/python/readability.py --root . --language python <changed-python-paths>` when the Python diff already owns class, `Protocol`, inheritance, public API, type-boundary, or dependency-direction evidence
- `python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>` for the same SOLID-sensitive Python diff set

## Core References

- `documents/coding-conventions-python.md`
- `documents/object-oriented-design.md`
- `documents/conventions/python/07_type_checker.md`
- `documents/REVIEW_PROCESS.md`

## Expected Outcome

- 型境界、API 影響、テスト不足、lint 逸脱が明示されている
- OOP readability evidence、SOLID principle signal、OOP dimension、finding kind が class / API 境界の review に結び付いている
- 実行した check と未実行の check が分かれている
- public behavior を変える差分なら docs / tests 追随も確認されている

## Mandatory Checklist

- `pyright` の結果を確認し、型エラーや warning を見逃していない
- `pytest tests/` の対象範囲が今回の変更に対して妥当である
- `ruff check python tests --select D,E,F,I,UP --ignore E501` の違反を確認している
- public function、CLI、config、serialization の境界を触った場合は call site 影響を見ている
- class、dataclass、`Protocol`、継承、public API、型境界、依存方向を持つ Python diff では、OOP readability report の SOLID principle signal を downstream evidence として確認している
- SOLID-sensitive Python diff では `check_solid_evidence.py` が changed path と OOP readability report の `scanned_paths` を対応付けている
- 例外処理、default 値、`Any` 境界、型 narrowing の崩れを見ている
- Python 実装に追随すべき docstring や docs があれば確認している

## Default Sequence

1. changed Python files と関連 test files を固定します。
1. `pyright` を見て型境界と import 破綻を確認します。
1. class、dataclass、`Protocol`、継承、public API、型境界、依存方向が変わる Python 差分では `$oop-readability-check` か `tools/oop/python/readability.py` を downstream evidence として使い、Single responsibility、Open/closed、Liskov substitution、Interface segregation、Dependency inversion の signal を確認します。
1. 同じ changed Python paths に対して `check_solid_evidence.py` を走らせ、OOP readability report の `scanned_paths` が review 対象を覆っていることを確認します。
1. `pytest tests/` で behavior を確認します。
1. `ruff check python tests --select D,E,F,I,UP --ignore E501` で style / import / docstring / upgrade 逸脱を見ます。
1. findings を API behavior、type safety、test coverage、docs drift に分けて返します。

## Common Failure Modes

- public API 変更に tests が追随していない
- `Any` や `Optional` の扱いが緩くなっている
- default 値や例外型が silently 変わっている
- import 順や docstring は直っているが behavior が壊れている
