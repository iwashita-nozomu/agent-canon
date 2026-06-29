# python-review
<!--
@dependency-start
contract skill
responsibility Documents python-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Reader Map

- Purpose: reviews Python diffs for type safety, tests, lint, API boundaries,
  OOP readability, and SOLID evidence.
- Use When: Python files, pyright findings, public APIs, typing boundaries, or
  Python reviewer routing are in scope.
- Section path: Purpose and Use When define triggers; 必須確認, 参照正本,
  期待される結果, 必須チェックリスト, and 標準順序 are the operational rules;
  よくある失敗 lists pitfalls.
- Boundary: this skill reviews Python changes; it does not replace the owning
  implementation or design route.

## Purpose

Python 差分を型、テスト、lint、境界設計の観点で厳密に確認します。

## Use When

- `python/` 配下を触る
- pyright 警告を扱う
- API や型境界を変える
- `bootstrap_agent_run.py` の変更パス判定で `python_reviewer` が自動で足された

## 必須確認

- `pyright`
- `pytest tests/`
- `ruff check python tests --select D,E,F,I,UP --ignore E501`
- 差分が定義順、公開入口の配置、内部補助関数の配置を変える場合は
  `python3 tools/agent_tools/check_convention_compliance.py`
- Python 差分が class、`Protocol`、継承、公開 API、型境界、依存方向の根拠を持つ場合は
  `python3 tools/oop/python/readability.py --root . --language python <changed-python-paths>`
- 同じ SOLID 対象の Python 差分には
  `python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>`

## 参照正本

- `documents/coding-conventions-python.md`
- `documents/object-oriented-design.md`
- `documents/conventions/python/07_type_checker.md`
- `documents/REVIEW_PROCESS.md`

## 期待される結果

- 型境界、API 影響、テスト不足、lint 逸脱が明示されている
- OOP 可読性根拠、SOLID 原則シグナル、OOP 次元、指摘種別が class / API 境界の review に結び付いている
- 実行した確認と未実行の確認が分かれている
- 公開挙動を変える差分なら文書とテストの追随も確認されている

## 必須チェックリスト

- `pyright` の結果を確認し、型エラーや警告を見逃していない
- `pytest tests/` の対象範囲が今回の変更に対して妥当である
- `ruff check python tests --select D,E,F,I,UP --ignore E501` の違反を確認している
- 公開関数、CLI、設定、直列化の境界を触った場合は呼び出し側への影響を見ている
- Python ファイル内の読者順序が、公開契約、公開入口、共有の内部補助関数、単一公開入口に
  従う内部補助関数の順で追えることを確認している
- 単一公開入口に従う内部補助関数が、その公開入口の直後にあることを確認している
- 複数入口で共有する内部補助関数が、公開入口群の直後にあることを確認している
- class、dataclass、`Protocol`、継承、公開 API、型境界、依存方向を持つ Python 差分では、OOP 可読性レポートの SOLID 原則シグナルを下流根拠として確認している
- SOLID 対象の Python 差分では `check_solid_evidence.py` が変更パスと OOP 可読性レポートの `scanned_paths` を対応付けている
- 例外処理、default 値、`Any` 境界、型 refinement の崩れを見ている
- Python 実装に追随すべき docstring や文書があれば確認している

## 標準順序

1. 変更された Python ファイルと関連テストファイルを固定します。
1. `pyright` を見て型境界と import 破綻を確認します。
1. 定義順を見て、公開契約、公開入口、内部補助関数が
   読者順序と依存順序に沿っていることを確認します。
1. class、dataclass、`Protocol`、継承、公開 API、型境界、依存方向が変わる Python 差分では `$oop-readability-check` か `tools/oop/python/readability.py` を下流根拠として使い、Single responsibility、Open/closed、Liskov substitution、Interface segregation、Dependency inversion のシグナルを確認します。
1. 同じ変更パスに対して `check_solid_evidence.py` を走らせ、OOP 可読性レポートの `scanned_paths` が review 対象を覆っていることを確認します。
1. `pytest tests/` で挙動を確認します。
1. `ruff check python tests --select D,E,F,I,UP --ignore E501` で style / import / docstring / upgrade の逸脱を見ます。
1. 指摘を API 挙動、型安全性、テスト網羅、文書ずれに分けて返します。

## よくある失敗

- 公開 API 変更にテストが追随していない
- `Any` や `Optional` の扱いが緩くなっている
- default 値や例外型が黙って変わっている
- import 順や docstring は直っているが挙動が壊れている
- 内部補助関数が離れた位置へ散り、公開入口から依存順序を追いにくい
