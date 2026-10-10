# research-workflow
<!--
@dependency-start
contract skill
responsibility Owns research-driven change: external evidence, comparison design, claim scope, and the post-run decision loop.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/algorithm-implementation-boundary.md equation-to-code boundary policy
upstream design ../../documents/experiments/experiment-critical-review.md critical evidence review
downstream design literature-survey.md source search and source packet owner
downstream design experiment-lifecycle.md single-run and rerun owner
downstream design adaptive-improvement-loop.md backlog-driven iteration owner
@dependency-end
-->

## Purpose

この skill は、外部調査、比較設計、実装変更、run、critical review、report review を
一つの research-driven outer loop として扱います。単一 run の実行は
`experiment-lifecycle`、文献の探索と source packet は `literature-survey`、複数回の
改善 backlog は `adaptive-improvement-loop` が所有します。

## Use When

- 外部調査を伴う実装または設計を行う
- benchmark、性能改善、method comparison を claim の根拠にする
- 数式、仮定、比較対象、適用範囲を明示してから実装したい
- 実験結果から claim、limitation、次の変更を更新する

## Procedure

研究上の問いと、結果から支えたい claim を特定します。比較 claim には同じ protocol
を適用した baseline/current evidence が必要です。数値問題では、結果を読むために必要な
problem setting、assumptions、stopping semantics と実装 path の対応を残します。
run の再現に必要な protocol、source、command、environment、seed、identity を記録し、
結論を plan-time の成功条件にせず runtime success や parity と同一視しません。

`literature-survey`、`experiment-lifecycle`、`experiment-review`、および
`report-writing` を、実際に外部資料、run、比較判断、または reader-facing report が
必要な範囲で使います。複数の変更を一緒に比較する場合は、設計がその帰属を支えない
限り個別効果を主張しません。結果を見た後は、説明更新、追加検証、fresh rerun、次の
変更、または範囲を限定した終了のうち、evidence が支持する次の action を選びます。
以下の state 名は代表例であり、すべての task が同じ branch を通る必要はありません。

- `report_rewrite_required`: 同じ result の説明を直す
- `extra_validation_required`: 同じ仮説・protocol を保った追加検証
- `rerun_required`: protocol または実装を直して新しい run identity を作る
- `approved`: 指定範囲で次の action が決まった。これは claim 受理を意味しない

## Evidence Reading

- correctness evidence と performance evidence を分ける。parity test は速度の根拠にせず、
  speedup は数式上の正しさの根拠にしない
- raw failure count だけで判断せず、case mix、failure kind、success rate、environment noise を分ける。
- 同じ case set と denominator で代表値とばらつきを比較する。
- 改善した指標の背後にある悪化（速度と失敗率、精度と memory など）を同じ record に残す
- toy-only、baseline 未比較、一つの difficulty 帯だけの結果から scalability、superiority、
  trainer replacement、広い theorem を主張しない
- `Results` は観測、`Discussion` は解釈、`Limitations` は言えない範囲として分ける
- claim は source と artifact に辿れるようにし、推測を観測事実として書かない

Run note には、解釈に必要な問い・比較・protocol、変更、観測、limitation、decision、
next action、および利用した commit/run path を残します。artifact identity と report の
構成はそれぞれの owner に委譲します。

## Boundary

- 外部 source の検索、採否、反証、URL / DOI / access / cache metadata、citation-ready
  record は `literature-survey` が所有する。research はその source packet を消費して
  source claim と task claim の境界を保つ
- 単一 run、terminal status、rerun、実行 provenance は `experiment-lifecycle` が所有する
- 実在 artifact の role、checksum、readback、retention は `result-artifact-writeout` が所有する
- 複数 iteration の backlog、budget、next item は `adaptive-improvement-loop` が所有する
- 数値アルゴリズムの式、収束、failure semantics は `computational-optimization` を追加する
- reader-facing report の本文・制限・引用導線は `report-writing` を追加する
- この skill は実験 runner、結果ファイル、一般的な repo feature delivery の代替ではない
