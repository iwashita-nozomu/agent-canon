<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# テスト規約（共通）

この文書は、`tests/` 配下のテストを対象にします。

## 🚀 クイックリファレンス

**初めての場合**: まずこのセクションをお読みください

| 用途 | コマンド | 詳細 |
|---|---|---|
| **最初の pytest 実行** | `pytest tests/<subdir>/test_*.py -v` | → [実行方法](#32-標準出力を表示する) |
| **ユニットテスト作成** | 想定解 + 比較検証 | → [想定解](#4-想定解と標準出力ログ) |
| **統合テスト設計** | 異なるレイヤー・複数ケース | → [分類](#2-配置と分類) |
| **エッジケーステスト** | 乱数 seed 固定 + 悪条件 | → [乱数](#5-乱数大規模テスト) |
| **テスト失敗の診断** | JSON ログを `tests/logs/` 確認 | → [実行方法](#3-実行方法) |

---

## 1. 対象と目的

- 対象は `tests/` 配下のテストです。
- 目的は、再現可能な数値検証とログ保存の運用を揃えることです。

## 2. 配置と分類

- テストは `tests/` に集約します。
- 分類は次の通りです。
  - `tests/<package>/`: library / package 単位の unit test。
  - `tests/tools/`: repo script や補助 tool の test。
  - `tests/experiment_runner/`: 汎用 experiment runtime の test。
  - `tests/integration/`: package をまたぐ結合 test。
- 大規模ケースは `case` や `*_large` の名称で明示します。

## 3. 実行方法

- **pytest を基本**にし、一括実行を標準とします。
- テストは `tests/` を対象に収集します。
- `if __name__ == "__main__":` による単体実行は **補助的に許可**します。
- 各テストファイルは `_run_all_tests()` を定義し、`if __name__ == "__main__": _run_all_tests()` の形で単体実行できるようにします。

### 3.1 標準出力を表示する

- ファイル単位: `pytest -q -s tests/tools/test_run_managed_experiment.py`
- 全体: `pytest -q -s`

### 3.2 `python file.py` での補助実行

- どうしても単体で回したい場合は、`if __name__ == "__main__":` から `_run_all_tests()` を呼び出します。
- この補助実行でも、**計算結果は標準出力へ 1 行 JSON** で出力します。
- pytest fixture が必要な場合でも、`_run_all_tests()` から呼べる補助関数へ分離して両方から使えるようにします。

## 4. 想定解と標準出力ログ

- **想定解のあるテストは、必ず想定解を用意**します。
- その想定解を **標準出力に出力**し、結果と比較できるようにします。
- 1 行 1 レコードの辞書出力を基本にします。

### 4.1 推奨キー

- `case`: テスト名
- `expected`: 想定値
- `actual`: 実測値
- `rel_err` / `abs_err`: 誤差
- `seed`: 乱数 seed
- `dim` / `m` / `s` / `g`: 条件

## 5. 乱数・大規模テスト

- 乱数を使う場合は **固定 seed** を使用します。
- 悪条件・大規模ケースは **明示的に区別**し、ログに条件を出力します。

## 6. 禁止事項

- 本体モジュール内の `if __name__ == "__main__":` にテストを書きません。
- 例外のみを根拠にせず、**既知解・残差・反復回数**で検証します。
- repo 固有の directory 例を正本扱いせず、実在する `tests/` 配下だけを案内します。
