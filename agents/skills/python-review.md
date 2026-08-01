# python-review
<!--
@dependency-start
contract skill
responsibility Documents python-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ./catalog.yaml public skill and capability projection
upstream design ./skill-dependencies.yaml prerequisite and reviewer order
upstream design ./agent-orchestration.md canonical validation trust boundary owner
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse Python projection
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

## Validation route

validation scope の正本は
`agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary` です。
Python reviewer は親 packet の exact validation commands と、変更 mechanism に必要な
static/read-only confirmation を review します。`pytest tests/` や追加の full suite は、
親 packet の `validation_route` が明示した場合だけ扱い、reviewer が自動選択しません。
OOP readability と `check_solid_evidence.py` は、SOLID-sensitive な変更、または親 packet /
changed mechanism が明示的に required とした場合だけ mechanism-required confirmation に
含めます。単純な tooling、parser、docs、static change では自動追加しません。

## Use When

- `python/` 配下を触る
- `templates/experiments/_template/*.py` または Python Docstring projection を触る
- pyright 警告を扱う
- API や型境界を変える
- `bootstrap_agent_run.py` の変更パス判定で `python_reviewer` が自動で足された

## 必須確認

- 親 packet の `validation_route` にある exact validation commands
- 変更 mechanism が必要とする static/read-only confirmation。該当時の `pyright`、
  `bash tools/ci/run_python_quality_checks.sh` が選択する canonical Python owner path の
  Ruff、`python3 tools/agent_tools/check_convention_compliance.py`、OOP readability、
  `python3 tools/agent_tools/check_solid_evidence.py` はこの確認に含めます。
- `pytest tests/` は親 packet の exact command に含まれる場合だけ

## Docstring projection route

`agent_team.language_review_candidates` が Python implementation path（`python/`、`tests/`、
`.py` / `.pyi`）を含む changed surface に `python_reviewer` を候補として返した場合に、
この reviewer を起動します。convention/template documentation は同じ path inventory から
`docs_workflow_steward` が担当し、catalog capability は OOP/type design owner の選択に限ります。
semantic clause の owner は `documents/conventions/DOCSTRING_GUIDE.md` へ戻します。レビューは
Python syntax / format（Ruff D または pydocstyle）と、target の responsibility region に
選択した semantic delta が対応するかを確認します。signature、annotation、namespace、field
を重複記載せず、`Args`、`Returns`、`Raises` の全欄を意味契約の gate にしません。

## 参照正本

- `documents/conventions/coding-conventions-python.md`
- `documents/conventions/object-oriented-design.md`
- `documents/conventions/python/07_type_checker.md`
- `documents/conventions/REVIEW_PROCESS.md`

## 期待される結果

- 型境界、API 影響、テスト不足、lint 逸脱が明示されている
- validation route が選択した場合に、OOP 可読性根拠、SOLID 原則シグナル、OOP 次元、指摘種別が review に結び付いている
- 実行した確認と未実行の確認が分かれている
- 公開挙動を変える差分なら文書とテストの追随も確認されている

## 必須チェックリスト

- mechanism が要求する場合に `pyright` の結果を確認し、型エラーや警告を見逃していない
- 親 packet の exact validation commands と未実行項目を read back している
- `pytest tests/` を扱う場合は、親 packet が選んだ exact command の範囲だけを確認している
- mechanism-required な場合に、`bash tools/ci/run_python_quality_checks.sh` が選択する
  canonical Python owner path の Ruff 違反を確認している
- 公開関数、CLI、設定、直列化の境界を触った場合は呼び出し側への影響を見ている
- Python ファイル内の読者順序が、公開契約、公開入口、共有の内部補助関数、単一公開入口に
  従う内部補助関数の順で追えることを確認している
- 単一公開入口に従う内部補助関数が、その公開入口の直後にあることを確認している
- 複数入口で共有する内部補助関数が、公開入口群の直後にあることを確認している
- SOLID-sensitive な Python 差分、または親 packet / changed mechanism が required と明示した場合に、OOP 可読性レポートの SOLID 原則シグナルを下流根拠として確認している
- 上記の場合だけ `check_solid_evidence.py` が変更パスと OOP 可読性レポートの `scanned_paths` を対応付けている
- 例外処理、default 値、`Any` 境界、型 refinement の崩れを見ている
- Python 実装に追随すべき docstring や文書があれば確認している

## 標準順序

1. 変更された Python ファイルと関連テストファイルを固定します。
1. 親 packet の `validation_route` と、変更 mechanism に必要な static/read-only
   confirmation を read back します。
1. packet が選択した exact validation commands だけを確認します。`pytest tests/` が
   含まれる場合だけ、その command の挙動を確認します。
1. 定義順を見て、公開契約、公開入口、内部補助関数が
   読者順序と依存順序に沿っていることを確認します。
1. SOLID-sensitive な Python 差分、または親 packet / changed mechanism が required と明示した場合だけ `$oop-readability-check` か `tools/oop/python/readability.py` を下流根拠として使い、Single responsibility、Open/closed、Liskov substitution、Interface segregation、Dependency inversion のシグナルを確認します。
1. 上記の場合だけ同じ変更パスに対して `check_solid_evidence.py` を走らせ、OOP 可読性レポートの `scanned_paths` が review 対象を覆っていることを確認します。
1. mechanism が要求する場合だけ `pyright` または
   `bash tools/ci/run_python_quality_checks.sh` で型、style、import、docstring、upgrade
   の逸脱を見ます。
1. Python Docstring projection が変更された場合は、guide の DIC path / section / clause /
   evidence trace と Python adapter の syntax / format を read back します。
1. 指摘を API 挙動、型安全性、テスト網羅、文書ずれに分けて返します。

## よくある失敗

- 公開 API 変更にテストが追随していない
- `Any` や `Optional` の扱いが緩くなっている
- default 値や例外型が黙って変わっている
- import 順や docstring は直っているが挙動が壊れている
- 内部補助関数が離れた位置へ散り、公開入口から依存順序を追いにくい
