# コードの圧縮記述長

<!--
@dependency-start
contract design
responsibility Defines the Git snapshot scope and compression measurement.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/code_complexity.rs native CLI
@dependency-end
-->

`agent-canon code-complexity` は、Gitコミットから選んだ通常ファイルの件数、内容のバイト数、
復元可能なgzip記述のバイト数を返します。対象の既定値は `HEAD` です。基準を指定すると、
JSONの `delta` に対象値から基準値を引いた差が入ります。

``` bash
agent-canon code-complexity --root /path/to/repo --base origin/main --target HEAD -- src lib
```

`--` の後にリポジトリのルートからのファイル名またはディレクトリ名を指定します。
省略時はコミット内の全通常ファイルが対象です。混在リポジトリでは評価対象のコードをパスで指定します。
計測はコミット内のGitツリーとblobを読みます。スコープはモード `100644` と `100755` の
ファイルです。[Gitのツリーとblob](https://git-scm.com/docs/git-ls-tree)

## 記述長の定義

選択したファイル集合を $`T`$ とします。符号化 $`E(T)`$ は、Gitのツリー順で各ファイルの
「パス長・パスの生バイト列・実行属性・内容長・内容」を連結したバイト列です。パス長と内容長は
8バイトのリトルエンディアン整数、実行属性は通常モードが `0`、実行可能モードが `1` の1バイトです。
各フィールドの境界が決まるので、展開後のバイト列からファイルのパス、モード、内容を末尾まで復元できます。

実測値 $`L(T)`$ は $`E(T)`$ を、同梱の `flate2` のレベル6で1つのgzipストリームに圧縮した
出力のバイト数です。`gzip_bytes` はヘッダーと末尾を含む $`L(T)`$、`source_bytes` はファイル内容の
合計バイト数です。比較は同じ方式・AgentCanonリリース・パス範囲で行います。`v2` の測定値はパスと
実行属性を含むため、`v1` の記録がある比較では基準と対象の両方を `v2` で測り直します。

## コルモゴロフ複雑性との関係

最適な万能機械 $`U`$ を固定します。通常版のコルモゴロフ複雑性
$`C_U(x) = \min\{|p| : U(p)=x\}`$ は、$`x`$ を出力して停止する最短プログラム $`p`$ のビット長です。
$`C_U`$ は一般に計算不能です。固定したgzipデコーダで $`E(T)`$ を復元できるため、万能機械で
デコーダを実行する固定分のビット数 $`c_U`$ を含めて $`C_U(E(T)) \le 8 L(T) + c_U`$ が成り立ちます。
この上界から複雑性の値や候補間の順位は決まりません。
[Vitányi, How Incomputable Is Kolmogorov Complexity?](https://pmc.ncbi.nlm.nih.gov/articles/PMC7516884/)

`delta.gzip_bytes` は独立に圧縮した二つの記述長の差です。基準を入力として対象を復元する記述の
最短長は条件付きコルモゴロフ複雑性で定義されます。差分の符号は前者についてだけ解釈します。

## 格納量の比較

このツールは、選択したファイル集合のgzip格納量を比較するために使います。gzipは直近32 KiBまでの
重複を利用します。変数名、コメント、ファイル名、書式、ファイル順も測定値に影響します。
[DEFLATE仕様 §3.2](https://www.rfc-editor.org/rfc/rfc1951.html#section-3.2)
