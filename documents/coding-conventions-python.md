<!--
@dependency-start
responsibility Documents Python コーディング規約 for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
downstream design ./algorithm-implementation-boundary.md algorithm math-to-code boundary policy for Python implementations
downstream design ./object-oriented-design.md general OOP policy for Python class decisions
@dependency-end
-->

# Python コーディング規約

この文書は、`python/` と `tests/` を前提にした Python 実装向け規約の入口です。
特定 package 名や過去 project の前提は持ち込まず、template で再利用できる共通部分だけを残します。
厳格な実装と文書の書きぶりは `documents/coding-conventions-house-style.md` を併読してください。

## クイックスタート

| ステップ | 内容 | 詳細 |
|---|---|---|
| 1 | 対象範囲を確認 | [01_scope.md](./conventions/python/01_scope.md) |
| 2 | 公開境界の型注釈を決める | [04_type_annotations.md](./conventions/python/04_type_annotations.md) |
| 3 | アルゴリズム境界を決める | [algorithm-implementation-boundary.md](./algorithm-implementation-boundary.md) |
| 4 | OOP 境界を決める | [object-oriented-design.md](./object-oriented-design.md) |
| 5 | 配置と責務を決める | [09_file_roles.md](./conventions/python/09_file_roles.md) |
| 6 | 名前を確定する | [11_naming.md](./conventions/python/11_naming.md) |
| 7 | 数値リテラルの由来を確認 | [基本方針](./conventions/common/01_principles.md#数値ハードコード検証) |
| 8 | `pyright` と `pytest` を通す | [07_type_checker.md](./conventions/python/07_type_checker.md), [coding-conventions-testing.md](./coding-conventions-testing.md) |

## よくある間違い

```python
# NG: 公開境界なのに型がない
def load_config(path):
    return {"path": path}

# OK: 公開境界に型と契約がある
from pathlib import Path


def load_config(path: Path) -> dict[str, str]:
    """設定ファイルを読み込む。"""
    return {"path": str(path)}
```

## Docstring テンプレート

**モジュール docstring**

```python
"""module_name の概要。

このモジュールは [責務] を担当します。

公開インターフェース:
    PublicClass: [簡潔な説明]
    public_function: [簡潔な説明]

参考資料:
    - documents/coding-conventions-python.md
"""
```

**関数 docstring**

```python
from pathlib import Path


def load_config(path: Path) -> dict[str, str]:
    """設定ファイルを読み込む。

    Args:
        path: 設定ファイルへの path。

    Returns:
        読み込んだ設定値。

    Raises:
        FileNotFoundError: path が存在しない場合。
    """
```

## 現在の対象

- `python/` 配下の checked-in Python package と共有 runtime
- `tests/` 配下の pytest ベースのテスト
- Python で書かれた `scripts/` のうち、repo 運用の正面入口になるもの
- JAX のような framework 固有ルールは、必要な repo だけ補足として読みます

## 行長

- 固定の 100 文字制限を Python 規約にしません。
- 長い import、URL、dependency header、型注釈、表形式データなどは、無理に折り返して機械可読性や検索性を落とさないでください。
- 行長は lint の fail 条件ではなく、可読性、既存 formatter、project-local `pyproject.toml` の明示設定に従って判断します。
- Ruff を使う repo では、行長だけを理由に fail させたくない場合、`E501` を ignore します。

## Import と責務境界

- 未使用 import、wildcard import、責務外 local import は変更に残しません。
- 追加した import が local file に解決できる場合は、repo top-level
  `responsibility-scope.toml` の `[[import_rule]]` に沿う必要があります。
- 既存 scope を越える import が必要な場合は、先に設計上の依存方向を確認し、
  scope rule を更新するか、薄い adapter を既存責務側へ置きます。
- `python3 tools/agent_tools/import_responsibility.py --changed` を
  `ruff F401` より前の軽量 gate として使い、tool rejection を実装前に予測します。

## 目次

1. [対象](./conventions/python/01_scope.md)
2. [関数の型注釈](./conventions/python/04_type_annotations.md)
3. [コメント](./conventions/python/06_comments.md)
4. [型チェッカの活用](./conventions/python/07_type_checker.md)
5. [責務分離](./conventions/python/09_file_roles.md)
6. [アルゴリズム境界](./algorithm-implementation-boundary.md)
7. [OOP 境界](./object-oriented-design.md)
8. [命名規約](./conventions/python/11_naming.md)
9. テスト規約（共通）: [coding-conventions-testing.md](./coding-conventions-testing.md)
10. JAX 補足が必要な場合だけ: [15_jax_rules.md](./conventions/python/15_jax_rules.md)
11. ベンチマーク方針: [20_benchmark_policy.md](./conventions/python/20_benchmark_policy.md)
12. 実験ディレクトリ構成: [30_experiment_directory_structure.md](./conventions/python/30_experiment_directory_structure.md)

## Python ファイル修正後

- `python3 tools/agent_tools/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports`
- `python3 -m pyright`
- `python3 -m pytest tests/ -q --tb=short`
- `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501`

## Markdown ファイル修正後

- `make docs-check`
- 相対パスと参照先の存在を確認
- 必要なら `make ci` で Python と docs をまとめて確認
