<!--
@dependency-start
responsibility Documents 責務分離 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 責務分離

この章は、ディレクトリごとの責務分離だけを定めます。

## 要約

- この章では、どのディレクトリに何を置くかだけを定めます。
- クラスや Protocol の詳細設計は、この章では扱いません。
- API 詳細設計は、この章では扱いません。

## 規約

- `python/<package>/`: checked-in library code と shared runtime helper を置きます。
- `python/<package>/protocols.py`、`python/<package>/typing.py`、または `python/<package>/base/`: 共有の型境界と最下位レイヤを置きます。
- `python/experiment_runner/`: topic 非依存の experiment runtime を置きます。
- `tests/`: テストだけを置きます。
- `scripts/`: 実行補助とログ整形だけを置きます。
- `documents/`: 規約と設計書の一次情報源とします。
- `experiments/`: topic 固有の case 生成、実験本体、run artifact を置きます。
- C++ を使う場合、library 本体は `src/` と `include/` へ置き、`python/` に混ぜません。
