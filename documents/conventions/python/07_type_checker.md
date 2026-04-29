<!--
@dependency-start
responsibility Documents 型チェッカの活用 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 型チェッカの活用

この章は、pyright を中心とした型検査の運用方針を定めます。

## 要約

- cast ではなく pyright を優先します。
- 型の境界は repo 内の共有契約層へ集約します。

## 規約

- `pyright` の設定は `pyproject.toml` の `[tool.pyright]` を正本とします。
- repo root の `pyrightconfig.json` は editor / tool 互換のための薄いラッパーに限り、`extends = "./pyproject.toml"` だけを持たせます。独自設定は足しません。
- 既定の `pyright` 実行は repo root で行い、`pyproject.toml` に含めた対象だけを baseline として常時 clean に保ちます。
- 現在の baseline は `python/` と `tests/` 全体です。template 初期状態のように `tests/` だけが存在する段階でも、checked-in の Python ファイルを baseline として常時 clean に保ちます。
- VSCode / Pylance で third-party import を解決するときは、workspace で選ばれた Python interpreter が使われます。repo 側では `.vscode/settings.json` の `python.defaultInterpreterPath` を基準にし、差分がある場合は `Python: Select Interpreter` で合わせます。
- `tests/` を触った場合も、まず既定の `pyright` を通し、必要なら対象 path を明示して追加実行します。
- 実験段階やテストで `pyright` エラーが残る場合は、黙って放置せず `task.md`、`reviews/`、または関連 note に未解消として残します。
- cast 等のプログラマによる型安全性の確保は避け、pyright による型安全性の確保を優先します。
- 型の境界は package root 付近の `protocols.py`、`typing.py`、または typed dataclass に集約し、単一の基準で整合を保ちます。
- 契約 family を改名するときは、共有契約と domain 特化を同じ naming family で同時に更新します。
- `OldProblem` のような旧命名と `StructuredProblem` のような新命名を併存させません。
- 互換 alias を置いて一時しのぎにせず、参照箇所をまとめて更新して型境界を 1 系統に保ちます。
- `pyright: ignore` / `# type: ignore` の使用は避け、型注釈や設計側で解消します。

## 実行例

- baseline 全体: `pyright`
- テストを触ったとき: `pyright tests/<subdir-or-file>`
- 特定モジュールだけを確認したいとき: `pyright python/<subdir-or-file>`

### 例外（最小限の ignore）

- JAX の制御フローや dynamic な third-party API を含む式は、型チェッカが追従できず **実装上どうしても** `ignore` が必要になる場合があります。
- その場合は、次の条件をすべて満たす範囲で **最小限**に許可します。
  - まず boundary で型を正規化し、`ignore` を不要にできないか試す。
  - それでも解消できない場合のみ、`pyright: ignore` を 1 行単位で付ける。
  - `ignore` の直前に「なぜ解消できないか」を **丁寧にコメント**で説明する。
