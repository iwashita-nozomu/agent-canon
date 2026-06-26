<!--
@dependency-start
contract policy
responsibility Documents 責務分離 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# 責務分離

この章は、ディレクトリごとの責務分離だけを定めます。

## 要約

- この章では、どのディレクトリに何を置くかだけを定めます。
- Python file 内の定義は、読者順序と依存順序（dependency order）が追える単位で並べます。
- クラスや Protocol の詳細設計は、この章では扱いません。
- API 詳細設計は、この章では扱いません。

## 規約

- `python/<package>/`: checked-in library code と shared runtime helper を置きます。
- `python/<package>/protocols.py`、`python/<package>/typing.py`、または `python/<package>/base/`: 共有の型境界と最下位レイヤを置きます。
- pip installed `experiment_runner`: topic 非依存の experiment runtime として使います。
- `tests/`: テストだけを置きます。
- `scripts/`: 実行補助とログ整形だけを置きます。
- `documents/`: 規約と設計書の一次情報源とします。
- `experiments/`: topic 固有の case 生成、実験本体、run artifact を置きます。
- C++ を使う場合、library 本体は `src/` と `include/` へ置き、`python/` に混ぜません。

### Python File 内の定義順

- Python file は、module docstring、dependency header、`from __future__`
  import、標準 library import、third-party import、local import、公開契約、
  公開入口、内部実装、CLI / `main` entrypoint の順に並べることを必須にします。
- 公開契約には、公開 `TypeAlias`、`Protocol`、dataclass、公開 constant、
  `__all__` を含めます。
- 公開入口には、利用者が直接呼ぶ function、class、factory、CLI command
  handler を含めます。
- 内部実装は、共有 private helper、単一公開入口に従う private helper、
  serialization / formatting helper の順に並べます。
- 単一公開入口に従う private helper は、その公開入口の直後に置きます。
  複数入口で共有する private helper は、公開入口群の直後に置きます。
- class 内は、class-level contract、constructor、public methods、private
  methods、dunder methods の順に並べます。public methods はユーザーが辿る
  workflow order に合わせます。
- 例外: `dataclass` default factory、`typing.overload`、decorator target、
  registration table のように Python 評価順や型 checker が近接配置を必要とする
  場合は、近接配置を採用し、直前に `# 責務:` または短い理由コメントを置きます。

## 検証

- この文書の定義順規約は `python3 tools/agent_tools/check_convention_compliance.py`
  の `source_file_definition_order` marker contract で route coverage を確認します。
- 個別 Python file の定義順は、変更差分ごとの `python-review` と
  `check_convention_compliance.py` evidence で確認します。
