<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
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
| 3 | OOP 境界を決める | [object-oriented-design.md](./object-oriented-design.md) |
| 4 | 配置と責務を決める | [09_file_roles.md](./conventions/python/09_file_roles.md) |
| 5 | 名前を確定する | [11_naming.md](./conventions/python/11_naming.md) |
| 6 | `pyright` と `pytest` を通す | [07_type_checker.md](./conventions/python/07_type_checker.md), [coding-conventions-testing.md](./coding-conventions-testing.md) |

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

## 目次

1. [対象](./conventions/python/01_scope.md)
2. [関数の型注釈](./conventions/python/04_type_annotations.md)
3. [コメント](./conventions/python/06_comments.md)
4. [型チェッカの活用](./conventions/python/07_type_checker.md)
5. [責務分離](./conventions/python/09_file_roles.md)
6. [OOP 境界](./object-oriented-design.md)
7. [命名規約](./conventions/python/11_naming.md)
8. テスト規約（共通）: [coding-conventions-testing.md](./coding-conventions-testing.md)
9. JAX 補足が必要な場合だけ: [15_jax_rules.md](./conventions/python/15_jax_rules.md)
10. ベンチマーク方針: [20_benchmark_policy.md](./conventions/python/20_benchmark_policy.md)
11. 実験ディレクトリ構成: [30_experiment_directory_structure.md](./conventions/python/30_experiment_directory_structure.md)

## Python ファイル修正後

- `python3 -m pyright`
- `python3 -m pytest tests/ -q --tb=short`
- `python3 -m ruff check python tests --select D,E,F,I,UP`

## Markdown ファイル修正後

- `make docs-check`
- 相対パスと参照先の存在を確認
- 必要なら `make ci` で Python と docs をまとめて確認
