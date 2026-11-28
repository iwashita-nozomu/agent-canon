# コードの圧縮記述長

<!--
@dependency-start
contract design
responsibility Defines the Git snapshot scope and compression measurement.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/code_complexity.rs native CLI
downstream design ../../agents/skills/change-review.md generated code comparison
@dependency-end
-->

`agent-canon code-complexity` は、Gitのコミットに含まれるコードのファイル数、元のバイト数、
gzipで圧縮したバイト数を返します。対象と基準を指定すると、JSONの `delta` に対象値から基準値を
引いた差が入ります。対象の既定値は `HEAD` です。

``` bash
agent-canon code-complexity --root /path/to/repo --base origin/main --target HEAD -- src lib
```

`--` の後にリポジトリのルートからのファイル名またはディレクトリ名を指定します。
省略時はコミット内の全通常ファイルが対象です。混在リポジトリでは評価対象のコードをパスで指定します。
計測はGitのblobから元のバイト列を読みます。シンボリックリンク、サブモジュール、作業ツリー上の
未コミット内容は計測範囲の外です。[Gitのツリーとblob](https://git-scm.com/docs/git-ls-tree)

## 測定値の意味

計測器はGitのツリー順で各ファイルを読み、8バイトのリトルエンディアンの長さと内容を連結します。
このバイト列を1つのgzipストリームとして、AgentCanonが同梱する `flate2` のレベル6で圧縮します。
`source_bytes` はファイル内容の合計、`gzip_bytes` はgzipのヘッダーと末尾を含む出力サイズです。
出力には方式の識別子、比較に使ったパス、解決済みのコミットIDが入ります。

コルモゴロフ複雑性 $`K(x)`$ は、固定した計算機で $`x`$ を出力する最短のプログラム長で、
一般には計算不能です。gzipの出力は元データを復元できる記述の一例です。$`x`$ を上の連結バイト列、
$`L_{\mathrm{gzip}}(x)`$ を圧縮後のバイト数、$`c`$ をデコーダ等を記述する固定分のビット数とすると、
$`K(x) \le 8 L_{\mathrm{gzip}}(x) + c`$ です。実測値は圧縮器とファイル順に依存します。
比較には同じAgentCanonリリースとパス範囲を使います。
[Vitányi, How Incomputable Is Kolmogorov Complexity?](https://arxiv.org/abs/2002.07674)

同じ要件とテストを満たす生成コード候補を比較するとき、圧縮後のサイズはコードの記述量を調べる
補助指標になります。コメントや書式も入力に含まれます。正しさと保守性はテストとレビューで評価します。
