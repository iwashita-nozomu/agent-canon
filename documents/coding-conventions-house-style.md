<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# ハウススタイル規約

この文書は、この template の実装と正本文書に共通する書き方を固定する正本です。
単なる好みではなく、境界の明確化、型追跡、実行安全性、文書の単独可読性を守るためのルールとして扱います。

## 要約

- 公開境界は module docstring、`__all__`、先頭 `_` の命名で明示します。
- 非自明な関数と重要な処理塊には `# 責務:` コメントを付け、1 関数 1 責務を守ります。
- 入力検証、shape/dtype 正規化、例外送出は境界で先に行います。
- 型契約は `TypeAlias`、`Protocol`、型付き dataclass で表現し、`Any` と `cast` に逃げません。
- JAX を使う場合、trace 対象では `jax.lax.*` と配列演算を使い、Python 制御や暗黙変換を混ぜません。
- 正本文書は日本語で書き、`## 要約`、`## 規約`、`## 禁止事項`、`## 例外` を使い分けます。

## 規約

### 適用範囲

- `python/` 配下の実装とテストに適用します。
- Python で書かれた `scripts/` に適用します。
- `documents/`、`README.md`、`QUICK_START.md` などの人間向け正本文書に適用します。

### 1. モジュール入口

- 公開モジュールと package `__init__.py` には module docstring を必須にします。
- module docstring では責務、主要な公開要素、必要なら参照文書を明記しなければなりません。
- Python 実装ファイルでは `from __future__ import annotations` を先頭に置くことを必須にします。
- package `__init__.py` では `__all__` による公開 API の明示を必須にします。
- `from X import *` は禁止します。例外は package `__init__.py` だけとし、その場合でも直後に `__all__` で公開名を絞り込まなければなりません。

### 2. 名前と責務

- 公開 API 名は先頭 `_` を付けてはなりません。
- 内部 helper、内部状態、暫定実装は先頭 `_` を付けなければなりません。
- 非自明な関数、メソッド、内部 helper の直前には `# 責務:` コメントを 1 行で置くことを必須にします。
- 1 つの関数が複数段階の責務を持つことを禁止します。判定、変換、保存、通知を同時に抱え込んではなりません。
- `util`、`helper`、`misc`、`tmp`、`data` のような責務が読めない名前を公開 API に使うことを禁止します。

### 3. 型境界

- 外部に見える契約は `TypeAlias`、`Protocol`、型付き dataclass、または明示的な具象型で表現しなければなりません。
- アルゴリズム本体で `dict[str, Any]`、`tuple[Any, ...]`、`Callable[..., Any]` を契約として使うことを禁止します。
- `cast`、`# type: ignore`、`pyright: ignore` は型境界の設計で解決できる限り禁止します。
- `cast` を使う場合は、runtime 検証または shape/dtype 正規化を先に行い、直前コメントで理由を説明しなければなりません。
- 互換 alias を残して旧命名と新命名を併存させることを禁止します。型 family を変える場合は参照側も同時に更新します。

### 3.5 Protocol の整理

- repo-wide に共有する型境界、`TypeAlias`、基底 `Protocol` は最下位の共有レイヤにある `protocols.py` または `typing.py` に集約しなければなりません。
- domain に依存する特殊化は各 domain の `protocols.py` に置き、共有レイヤの汎用契約を継承して表現しなければなりません。
- `protocols.py` には契約だけを置き、重い実装、I/O、環境変数解釈、アルゴリズム本体を混ぜることを禁止します。
- `protocols.py` は実装 module を import してはなりません。依存は標準ライブラリ、型定義、最下位レイヤの契約に限定しなければなりません。
- 同じ概念の契約を複数の module に重複定義することを禁止します。既存契約を拡張できるなら継承し、新設は最後の手段にしなければなりません。
- 命名 family は `OptimizationProblem` / `OptimizationState` / `Constrained*` のように基底名を保存した特殊化で揃えなければなりません。
- 実験実行系のように共有数値基盤から独立した契約群は別 package の `protocols.py` に分離し、共有レイヤへ逆流させることを禁止します。
- 実装側は具体クラスに依存する前に `Protocol` で受けることを優先しなければなりません。ただし public 契約に不要な属性まで盛り込んではなりません。
- public に export する `Protocol`、`TypeAlias`、契約 family は `__all__` に必ず載せ、import 可能性をテストで確認しなければなりません。

### 4. 入力検証と正規化

- 公開関数、constructor、factory は入口で引数検証を済ませなければなりません。
- 契約違反には `ValueError` を使い、メッセージには対象の引数名と期待条件を含めなければなりません。
- shape、dtype、device 側表現への変換は境界で一度だけ行うことを必須にします。
- 暗黙の丸め、黙った clipping、条件付きの型すり替えを禁止します。補正が必要な場合は API か文書で明示しなければなりません。
- 環境変数の解釈は helper に集約し、アルゴリズム本体へ `os.getenv` を散在させることを禁止します。

### 5. JAX を使う場合の分離

- JAX を使う場合、host 側の組合せ列挙、参照実装、JSON 直列化前処理は NumPy/Python に寄せます。
- device 側で trace される数値計算は JAX 配列と `jax.numpy` / `jax.lax` に寄せなければなりません。
- trace 対象の反復に Python の `for`、`while`、`if` を持ち込むことを禁止します。`jax.lax.fori_loop`、`jax.lax.while_loop`、`jax.lax.scan` を使わなければなりません。
- trace 対象で `bool()`、`int()`、`float()` による JAX 配列の暗黙変換を禁止します。
- dtype を安定させる箇所では `jnp.asarray(..., dtype=...)` または `np.asarray(..., dtype=...)` を明示しなければなりません。

### 6. 状態と副作用

- 設定値、結果、完了通知のような不変データは `@dataclass(frozen=True)` を使うことを必須にします。
- mutable な dataclass は、進行中の process state や accumulator のように更新責務が明確な場合だけ許可します。
- library code での生 `print` を禁止します。デバッグは `jax.debug.print`、構造化ログ、または明示的な CLI 出力 helper を使わなければなりません。
- JSONL や report へ出す値は、直列化前に安全な型へ正規化しなければなりません。

### 7. テスト

- 数値アルゴリズムには既知解または参照実装との比較テストを必須にします。
- shape、dtype、単調改善、不変量、例外系のうち、対象機能に関係する項目を省略してはなりません。
- refine、prepare、cache、fallback を持つ実装では、互換性または改善方向のテストを必須にします。
- 乱数を使うテストでは seed の固定を必須にします。
- テスト用の参照実装では、可読性を優先した NumPy/Python ループを許可します。ただし本実装の複写にしてはなりません。

### 8. 文書

- 正本文書の主言語は日本語を必須にします。
- 各 Markdown 文書にはタイトル、短い導入、`##` 見出しごとの本文を必須にします。
- 規約文書には `## 要約` と `## 規約` を必須にします。
- 禁止事項がある場合は `## 禁止事項` を置くことを必須にします。
- 例外条件がある場合は `## 例外` を置き、条件と範囲を限定して書かなければなりません。
- 規約文書では `禁止`、`必須`、`しなければなりません`、`許可`、`任意` を使い、曖昧な規範表現を禁止します。
- `推奨` は非拘束な補足、読み順、参考情報にしか使ってはなりません。
- 正本文書は単体で概要と主要判断が読めるようにしなければなりません。リンク一覧だけの文書を作ることを禁止します。
- 実装や設計への参照は、責務や制約を説明するために必要な場合だけ書きます。ファイル列挙だけで本文を代替してはなりません。

## 禁止事項

- package `__init__.py` 以外での star import を禁止します。
- 型注釈のない公開関数を禁止します。
- 非自明な関数に `# 責務:` コメントがない状態を禁止します。
- 境界検証を後回しにして深い内部で失敗させることを禁止します。
- 正本文書に backup、proposal、dated report、run 固有メモを混ぜることを禁止します。
- 文書で `原則`、`望ましい`、`できれば`、`必要なら` を必須条件や禁止条件の代わりに使うことを禁止します。

## 例外

- `Protocol` のメソッド宣言、`@overload` の stub、dunder method、単純な property は `# 責務:` コメントを省略して構いません。
- serialization 境界、multiprocessing 境界、外部ライブラリ interop では `Any` や `cast` を最小限に許可します。ただし runtime 検証または前段の正規化を先に書かなければなりません。
- CLI entrypoint と運用スクリプトの人間向け表示では `print` を許可します。ただし library module へ漏らしてはなりません。
