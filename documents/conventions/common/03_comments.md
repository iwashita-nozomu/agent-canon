<!--
@dependency-start
responsibility Documents コメント for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# コメント

この章は、コメントの書き方に関する共通方針をまとめます。

## 要約

- 意図と前提を明確に書きます。
- 数式や数値安定性の注意を優先します。
- 各関数の責務を短いコメントで明示します。

## 規約

- コメントは丁寧に書き、意図と前提を明確にします。
- 仕様上の前提、数式の意味、数値安定性に関する注意を優先して記述します。
- 関数定義の直前には、**その関数が何を担当するか**を 1 行程度でコメントします。
- 実装の逐語説明ではなく、「何を判断しているか」「なぜその形にしているか」を優先します。
- 言語やモジュールに固有の補足は、各言語別規約で差分として書きます。
