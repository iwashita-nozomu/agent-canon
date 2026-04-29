<!--
@dependency-start
responsibility Documents 関数の型注釈 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 関数の型注釈

この章は、関数の型注釈に関する最低限のルールをまとめます。

## 要約

- 公開境界の引数・戻り値には必ず意味のある型を付けます。
- 裸の `Any` や曖昧な container 型で境界を済ませません。

## 規約

- 公開関数、public method、factory、CLI entrypoint の引数・戻り値には型注釈を必須にします。
- 標準ライブラリ型だけで十分に意味が伝わるなら、`Path`、`Sequence[str]`、`Mapping[str, str]` のような明示的な型を使います。
- domain の意味を共有したい場合だけ、repo-wide に定義した `TypeAlias`、`Protocol`、typed dataclass を使います。
- `Any`、`dict[str, Any]`、`tuple[Any, ...]` を public 契約の第一候補にしてはなりません。
- 互換性のために曖昧な基底型を露出するより、呼び出し側が守るべき最小契約を名前付き型で表現します。

## 実行設定の受け渡し

dtype、backend、device、execution policy のように結果へ影響する設定は、public 境界で解決して内部へ明示的に渡します。

- 公開 API が設定を受け取る必要がある場合は、typed config object か明示的な keyword 引数で受けます。
- 内部 helper は解決済みの設定値を引数で受け取り、module global や環境変数を直接参照しません。
- 暗黙の既定値が重要な意味を持つ場合は、docstring と type annotation の両方で表現します。
