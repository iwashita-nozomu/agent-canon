# Literature Intake

## 目的

- 論文や本を読んで note に落とすときの最短手順をそろえる。
- 後から「どの文章がどの文献のどこか」を追えるようにする。

## 基本方針

- まず標準的な論文、教科書、サーベイがあるか確認する。
- いきなり project 内の観測だけで一般論を書かない。
- 本文の主張には、できるだけ近い位置で `Source:` を付ける。
- 実験から得た内容は `Observation:`、自分の判断は `Consideration:` や `Idea:` で分ける。

## PDF を読む順番

- 最初に表紙と目次を見る。
- 次に、使いたい主張に関係する章と節を特定する。
- そのあと、その節の前後 1-2 ページを読む。
- いきなり全文を読もうとしない。

## まず探すとよいもの

- 定義
- 主定理
- 誤差評価
- アルゴリズムの概要
- データ構造や実装方針
- 制約や前提条件

## PDF 以外を優先できるもの

- HTML 版があるなら、まず HTML を使う。
- TeX source があるなら、数式や定理番号を拾うときに便利。
- arXiv source があるなら、section や equation を追いやすい。
- PDF しかないときは、本文引用より section と page を丁寧に残す。

## 実務上のコツ

- まず file 名だけでなく、著者、年、題名を note に書く。
- local path が必要な場合は、それも書く。
- `p. 58, Eq. (4.5)` のように、ページと式番号を残す。
- `Chapter 4` のような章レベル参照も使う。
- 1 つの主張に 2 本以上の文献が効いているなら、役割を分けて書く。

## よくある失敗

- 参考文献を末尾に並べるだけで、本文との対応がない。
- project 内の観測と文献上の一般論が混ざる。
- PDF の表現を雑に言い換えて、どこを引いたか分からなくなる。
- 読めない PDF を reference に入れたまま、本文で強く依存する。

## 使いやすい書き方

- `Source: Holtz 2010, p. 58, Eq. (4.5)`
- `Source: Murarasu 2013, p. 43-49`
- `Observation: partial JSON の集計結果に基づく`
- `Consideration: 上の 2 つから、この project では保持戦略が支配的だと考える`

## References

- [Markus Holtz, Sparse Grid Quadrature in High Dimensions with Applications in Finance and Insurance, 2010](/workspace/references/978-3-642-16004-2.pdf)
- [Adina-Eliza Murarasu, Advanced Optimization Techniques for Sparse Grids on Modern Heterogeneous Systems, 2013](/workspace/references/sparse_grid/Murarasu_2013_PhD_Advanced_Optimization_Techniques_for_Sparse_Grids_on_Modern_Heterogeneous_Systems.pdf)
