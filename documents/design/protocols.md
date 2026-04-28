<!--
@dependency-start
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
downstream design ../object-oriented-design.md consumes Protocol boundary rules
@dependency-end
-->

# Protocol 設計

この文書は、repo における `Protocol`、`TypeAlias`、契約 family の置き方と依存方向を定める設計正本です。
実装詳細ではなく、どの層にどの契約を置くか、どこまでを共有契約にするかを固定します。

## 要約

- 共有契約は最下位の共有レイヤにある `protocols.py` または `typing.py` に集約します。
- domain 特化の契約は各 package の `protocols.py` で、共有契約の特殊化として定義します。
- `protocols.py` は契約だけを持ち、実装や I/O を持ち込みません。
- 契約の依存方向は一方向に固定し、上位実装から下位契約へ逆流させません。
- public 契約は `__all__` と import テストで露出を固定します。

## 規約

### 1. レイヤ

| レイヤ | 配置 | 役割 | 依存先 |
|---|---|---|---|
| 共有契約 | `python/<package>/protocols.py` または `python/<package>/base/protocols.py` | 共有 `TypeAlias`、共有 `Protocol`、cross-domain な契約 family | 標準ライブラリ、最小の型ライブラリ |
| domain 契約 | `python/<package>/<domain>/protocols.py` | domain 専用の型と共有契約の特殊化 | 共有契約、domain の最小型定義 |
| 実験実行契約 | `python/experiment_runner/protocols.py` | runner / scheduler / worker の軽量契約 | 標準ライブラリ、同 package の最小型定義 |
| 実装 | `python/**/{*.py}` | 契約の具象実装 | 対応する `protocols.py` |

### 2. 共有 `protocols.py` に置くもの

- 複数 domain で再利用する `TypeAlias`
- 問題設定や task context のような汎用 `Protocol`
- 複数 package にまたがっても意味が変わらない最下位レイヤの契約

次は共有 `protocols.py` に置いてはなりません。

- 特定 domain にしか現れない補助属性
- 実験実行系だけが使う runner 契約
- I/O、ログ、環境変数、プロセス制御の実装都合

### 3. domain `protocols.py` に置くもの

- `Vector`、`Function`、`Params` など domain 固有の変数空間
- `OptimizationProblem[T]` の特殊化
- domain の実装が共有する最小限の振る舞い契約

次の条件を満たさない新規 `Protocol` 追加を禁止します。

- 2 個以上の実装または call site が共有する
- 具象クラス名ではなく振る舞いで受けたい理由がある
- 既存 `Protocol` の特殊化では表現できない

### 4. `experiment_runner/protocols.py` の扱い

- `TaskContext`、`Worker`、`Scheduler`、`Runner` のような runtime 契約は数値基盤から独立させます。
- `experiment_runner` の契約を共有 package の `protocols.py` に混ぜることを禁止します。
- 逆に、`experiment_runner` 実装が数値 domain の契約へ依存しないことを維持します。

### 5. 命名

- 基底名は 1 つに固定し、特殊化でもその基底名を保存します。
  - 例: `TaskContext` -> `RemoteTaskContext`
  - 例: `OptimizationProblem` -> `VectorOptimizationProblem`
- 制約や環境差分は prefix か suffix のどちらか一方で統一します。
- 旧命名と新命名の互換 alias を併存させることを禁止します。

### 6. 依存方向

- 共有 `protocols.py` は上位 domain package を import してはなりません。
- 各 domain `protocols.py` は実装 module を import してはなりません。
- 実装 module は対応する `protocols.py` を import して構いません。
- 契約同士の相互 import を禁止します。共通要素が必要なら下位レイヤへ降ろします。

### 7. 公開境界

- public 契約は `__all__` に載せなければなりません。
- package `__init__.py` が再 export する場合も、公開名を `__all__` で固定しなければなりません。
- public 契約 family を追加・改名した場合は import テストを更新しなければなりません。

## 禁止事項

- `protocols.py` にアルゴリズム本体を置くことを禁止します。
- 契約のためだけに上位 package を import することを禁止します。
- 同じ概念の `Protocol` を別名で重複定義することを禁止します。
- `Any` だらけの巨大 context を一般 domain の契約へ持ち込むことを禁止します。
- 具象実装が 1 つしかなく、差し替え境界もないのに `Protocol` を増やすことを禁止します。

## 例外

- `TaskContext` のような runtime 境界で構造が広く開くものは `TypeAlias = dict[str, Any]` を許可します。ただし package をまたぐ一般契約へ昇格させてはなりません。
- 外部ライブラリの structural typing に合わせるための最小限の `Protocol` は許可します。ただし public API へ露出させる場合は `__all__` とテストを付けなければなりません。
