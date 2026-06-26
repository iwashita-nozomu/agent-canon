<!--
@dependency-start
contract policy
responsibility Documents Python の配置と定義順 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# Python の配置と定義順

この章は、Python 実装の配置先と、ファイル内の定義順を定めます。

## 要約

- ディレクトリごとに置くものを固定します。
- Python ファイル内の定義は、読者順序と依存順序が追える単位で並べます。
- クラスや Protocol の詳細設計は、この章では扱いません。
- API 詳細設計は、この章では扱いません。

## 文書動線

- すべての言語に共通する書き方は
  [ハウススタイル規約](../../coding-conventions-house-style.md) を見ます。
- Python 全体の規約は [Python コーディング規約](../../coding-conventions-python.md) を見ます。
- Python 差分の確認手順は [python-review](../../../agents/skills/python-review.md) を見ます。
- この章は、配置先と定義順だけを判断する入口です。

## 規約

- `python/<package>/`: Git 管理対象のライブラリコードと共有実行補助を置きます。
- `python/<package>/protocols.py`、`python/<package>/typing.py`、または `python/<package>/base/`: 共有の型境界と最下位レイヤを置きます。
- pip で導入した `experiment_runner`: 主題非依存の実験実行基盤として使います。
- `tests/`: テストだけを置きます。
- `scripts/`: 実行補助とログ整形だけを置きます。
- `documents/`: 規約と設計書の一次情報源とします。
- `experiments/`: 主題固有のケース生成、実験本体、実行成果物を置きます。
- C++ を使う場合、ライブラリ本体は `src/` と `include/` へ置き、`python/` に混ぜません。

### Python ファイル内の定義順

- Python ファイルは、モジュール docstring、依存ヘッダー、`from __future__`
  import、標準ライブラリ import、外部ライブラリ import、ローカル import、
  公開契約、公開入口、内部実装、CLI / `main` 入口の順に並べることを必須にします。
- 公開契約には、公開 `TypeAlias`、`Protocol`、dataclass、公開 constant、
  `__all__` を含めます。
- 公開入口には、利用者が直接呼ぶ関数、class、生成関数、CLI command handler を含めます。
- 内部実装は、共有の内部補助関数、単一公開入口に従う内部補助関数、
  直列化 / 整形の内部補助関数の順に並べます。
- 単一公開入口に従う内部補助関数は、その公開入口の直後に置きます。
  複数入口で共有する内部補助関数は、公開入口群の直後に置きます。
- class 内は、class-level contract、constructor、公開メソッド、内部メソッド、
  dunder method の順に並べます。公開メソッドは利用者が辿る処理順に合わせます。
- 例外: `dataclass` default factory、`typing.overload`、decorator target、
  registration table のように Python 評価順や型チェッカが近接配置を必要とする
  場合は、近接配置を採用し、直前に `# 責務:` または短い理由コメントを置きます。

## 検証

- この文書の定義順規約は `python3 tools/agent_tools/check_convention_compliance.py`
  の `source_file_definition_order` marker contract で経路の網羅を確認します。
- 個別 Python ファイルの定義順は、変更差分ごとの `python-review` と
  `check_convention_compliance.py` の根拠で確認します。
