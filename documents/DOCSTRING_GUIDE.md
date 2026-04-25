<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Docstring ガイドと `__all__` 統一ルール

## 概要

このドキュメントは、docstring 欠落と `__all__` 定義の不統一を改善するための正本ガイドです。

## 📝 Docstring 実装ガイド

### なぜ docstring が重要なのか？

- **自動ドキュメント生成**: Sphinx や MkDocs で自動抽出
- **IDE 統合**: ホバー表示で関数説明が即座に確認できる
- **保守性向上**: 実装者の意図が明確になる
- **規約遵守**: コーディング規約で明示的に要求

**規約**: [documents/coding-conventions-python.md](./coding-conventions-python.md)

## 📋 実装パターン

### 1. モジュール Docstring（**必須**）

**ファイル先頭に配置**

```python
"""module_name パッケージの概要（1行）。

このモジュールは[責務]を担当します。
- 主要機能1
- 主要機能2

公開インターフェース:
    PublicClass: [説明]
    public_function: [説明]

参考資料:
    - documents/coding-conventions-python.md
    - [リンク]

実装例:
    >>> from project_package.module_name import PublicClass
    >>> obj = PublicClass(...)
"""

from __future__ import annotations

# ... import 以下のコード ...
```

**チェックリスト**:

- [ ] モジュールの目的が明確
- [ ] 公開シンボルがリストアップされている
- [ ] 参考資料・リンクが明示

______________________________________________________________________

## 2. クラス Docstring（**必須**）

```python
class JobResult:
    """ジョブ結果の値オブジェクト。

    実行結果の主要メタデータを保持します。
    集計や report 作成はこの型を通して行います。

    Attributes:
        name (str): ジョブ名
        status (str): 完了状態
        duration_sec (float): 実行時間

    See Also:
        JobSummary: 集計用の上位表現

    Example:
        >>> result = JobResult(name="smoke", status="passed", duration_sec=1.2)
        >>> result.status
        'passed'
    """
```

**チェックリスト**:

- [ ] クラスの役割が1行で明確
- [ ] 重要なメソッドやプロパティを記載
- [ ] 使用例が含まれている

______________________________________________________________________

## 3. 関数 Docstring（**必須**）

```python
from pathlib import Path


def load_registry(path: Path) -> dict[str, str]:
    """registry 定義を読み込む。

    Args:
        path: registry file への path。

    Returns:
        topic 名を key に持つ辞書。

    Raises:
        FileNotFoundError: path が存在しない場合。
        ValueError: registry 内容が壊れている場合。

    Example:
        >>> registry = load_registry(Path("experiments/registry.toml"))
        >>> "default" in registry
        True
    """
    ...
```

**チェックリスト**:

- [ ] 関数の目的が1文で説明されている
- [ ] Args に全パラメータが記載
- [ ] Returns が戻り値の型と意味を説明
- [ ] Raises で例外を記載
- [ ] Example で実行可能なコード例

______________________________________________________________________

## 🏷️ `__all__` 定義ガイド

### 目的

- **公開 API の明示**: ユーザーが `from module import *` で何を得るか明確にする
- **型チェッカーの支援**: Pylance が `__all__` から公開シンボルを推論
- **ドキュメント生成**: Sphinx がこれを元に API ドキュメント作成

### 実装パターン

**基本形式**:

```python
__all__ = [
    "PublicClass",
    "public_function",
    "PUBLIC_CONSTANT",
]
```

**ルール**:

- 大文字・小文字を正確に
- アルファベット順でソート（推奨）
- プライベート（`_` prefix）は含めない
- 型チェッカー用のシンボルも含める

### 悪い例 ❌

```python
# NG: __all__ がない
def public_func():
    pass

def _private_func():
    pass

# NG: プライベート関数を公開
__all__ = ["public_func", "_private_func"]

# NG: from X import *
from . import some_module as *
```

## 良い例 ✅

```python
"""エクスポート構造を明示。"""

from typing import Protocol

class Operator(Protocol):
    """演算子プロトコル。"""
    pass

class MyClass:
    """パブリッククラス。"""
    pass

def my_function():
    """パブリック関数。"""
    pass

# 公開インターフェースを明示
__all__ = [
    "MyClass",
    "Operator",
    "my_function",
]
```

## 📊 チェックリスト

### 新規ファイル作成時

- [ ] モジュール docstring を先頭に追加
- [ ] `__all__` を定義（公開シンボルがある場合）
- [ ] すべてのパブリッククラスに docstring を追加
- [ ] すべてのパブリック関数に docstring を追加
- [ ] `from X import *` を使わない

### 既存ファイル修正時

- [ ] 修正対象のクラス/関数に docstring を追加
- [ ] 例があれば Example セクションを追加
- [ ] `__all__` が存在する場合、修正内容を反映
- [ ] `pyright --outputjson` で型チェック実行

______________________________________________________________________

## 🔧 自動チェック

### ローカル実行

```bash
# docstring チェック（pydocstyle）
pydocstyle python tests

# スタイル + import + docstring チェック（ruff）
ruff check python tests --select D

# 型チェック
pyright
```

## CI/CD パイプライン

```bash
# make ci で実行
make ci

# または手動実行
bash tools/ci/run_all_checks.sh
```

______________________________________________________________________

## 📈 改善の段階

### フェーズ 1（今週）

- [ ] モジュール docstring をすべてのファイルに追加
- [ ] `__all__` を未定義ファイルに追加

**所要時間**: 1-2 時間

### フェーズ 2（来週）

- [ ] 既存クラスに docstring を追加
- [ ] 既存関数に docstring を追加
- [ ] Example セクションを充実

**所要時間**: 4-6 時間

### フェーズ 3（完成）

- [ ] Sphinx でドキュメント生成テスト
- [ ] CI パイプラインに自動チェック統合
- [ ] チームレビュー

______________________________________________________________________

## 参考資料

- [Google Python Style Guide - Comments and Docstrings](https://google.github.io/styleguide/pyguide.html)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [NumPy Docstring Standard](https://numpydoc.readthedocs.io/en/latest/format.html)
- [documents/coding-conventions-python.md](./coding-conventions-python.md)
