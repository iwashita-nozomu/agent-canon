<!--
@dependency-start
contract policy
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

## この文書の読み方

この入口文書は、Python 実装で最初に確認する scope、型注釈、アルゴリズム境界、OOP、配置、命名、数値リテラル、pyright / pytest の導線をまとめます。まずクイックスタートで関連規約へ飛び、よくある間違いと Docstring テンプレートで公開境界の最小形を確認します。後半は行長、import と責務境界、helper-first 禁止、SOLID、目次、変更後チェックを読むための索引です。

## クイックスタート

| ステップ | 内容 | 詳細 |
|---|---|---|
| 1 | 対象範囲を確認 | [01_scope.md](./conventions/python/01_scope.md) |
| 2 | 公開境界の型注釈を決める | [04_type_annotations.md](./conventions/python/04_type_annotations.md) |
| 3 | アルゴリズム境界を決める | [algorithm-implementation-boundary.md](./algorithm-implementation-boundary.md) |
| 4 | OOP / SOLID 境界を決める | [object-oriented-design.md](./object-oriented-design.md) |
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

## Library と helper-first の禁止

- code edit の前に原因調査を残します。少なくとも `Observation:`、
  `Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、
  `Validation Before Edit:` / `Support Evidence:` を run artifact、issue、または
  design note に書き、どの code path をなぜ触るかを明確にします。
- vendored dependency、installed package、`site-packages`、`node_modules` の
  library implementation を直接書き換えません。必要な場合は wrapper /
  adapter、fork / upstream patch、または manifest-backed vendor import として
  扱います。
- 実装の最初の一手として helper-like function を増やしません。先に owning
  class / module contract、責務 scope、issue、docs、test のいずれかで境界を
  固定し、既存 helper / API を再利用できない理由を明示します。
- identity return、pass-through wrapper、同じ normalized body を持つ duplicate
  helper は冗長 helper として扱います。`helper_function_inventory.py` の
  `redundant_helper`、`redundancy_rule`、`redundant_with` を見て、既存実装へ
  統合するか、残す理由を design / issue に書きます。
- helper / local function の名前は、推定 role に対応する action token を含めます。
  `python3 tools/agent_tools/helper_function_inventory.py --changed --baseline-ref HEAD --only-name-gaps`
  は、責務検索で再利用候補として見つけやすい名前へ寄せる review 対象を出します。
- `.codex/hooks/library_implementation_guard.py` と
  `.codex/hooks/helper_first_guard.py` はこの規約の edit-time gate です。
- `.codex/hooks/cause_investigation_guard.py` は code edit 前の cause evidence
  gate です。

## SOLID 設計契約

Python 実装で class、dataclass、`Protocol`、継承、public API、型境界、依存方向を
触る場合は、[オブジェクト指向設計方針](./object-oriented-design.md) と
`tools/oop/python/readability.py` を SOLID principle signal の primary OOP evidence route にします。
`tools/oop/shared/readability_core.py` の `SOLID_PRINCIPLES_BY_KIND` が finding kind から
SOLID 見出しへの機械投影を所有します。
`tools/agent_tools/check_solid_evidence.py` は SOLID-sensitive な Python 差分と
OOP readability report の `scanned_paths` coverage を照合します。

| Principle | Python coding contract | Static risk signal |
|---|---|---|
| Single responsibility | domain calculation、IO、persistence、rendering、orchestration、reporting を責務語彙で分ける。 | OOP readability の large boundary、mixed effect、vague name、helper bucket、identity/pass-through finding |
| Open/closed | 予測済み variant は `Protocol`、value object、registry、adapter、別 entrypoint で拡張軸に置く。 | OOP readability の `Optional` / `None` runtime routing、deep variant branch、cognitive complexity signal |
| Liskov substitution | subtype / subclass / protocol implementation は base contract、入力条件、戻り値、例外、invariant を保存する。 | type checker、shared behavior tests、OOP readability の base class signal |
| Interface segregation | caller が使う最小 role を `Protocol` または role-specific public surface にする。 | OOP readability の public method / field / parameter breadth signal |
| Dependency inversion | high-level policy は stable abstraction、typed dataclass、`Protocol`、composition root へ依存を寄せる。 | OOP readability の annotation / optional boundary signal。import / layer 方向は `import_responsibility.py` と dependency review の supporting evidence |

SOLID / OOP 境界の検証は、pytest wrapper ではなく該当 checker command を validation route に置きます。
repo-wide review では `$oop-readability-check` を使い、Markdown / JSON report の
SOLID principle signal counts、OOP dimension、finding kind、`path:line` を design artifact に引用します。
closeout では `python3 tools/agent_tools/check_solid_evidence.py --changed --evidence <oop-readability-report>`
で、SOLID-sensitive な path と OOP readability evidence の対応を確認します。

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

- `tools/bin/agent-canon docs check`
- 相対パスと参照先の存在を確認
- 必要なら `make ci` で Python と docs をまとめて確認
