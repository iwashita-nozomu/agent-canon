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

実装または正式な run の前に、`Question`、`Scope`、`Comparison Target`、
`Evidence Targets`、`Protocol`、`Operational Stop Condition` を一つの note に固定します。
数値問題では問題設定・仮定・停止条件と実装 path の対応も残します。研究上の結論を
plan-time の成功条件にせず、runtime success や parity を claim と同一視しません。

1. `$literature-survey` の source packet を受け取り、source claim と task claim の対応を決める。
2. baseline/current state を同じ protocol で記録する。
3. 一つの code、protocol、または runtime change を選ぶ。複数種類を一 iteration に混ぜない。
4. `$experiment-lifecycle` で fresh run を行い、source・command・環境・seed・run identity を残す。
5. `$experiment-review` で比較、仕様・数式との一致、trade-off、overclaim を確認する。
6. 必要なら `$report-writing` で reader-facing report を作り、次の状態を一つ選ぶ。

Decision は次の post-run state に限定します。

- `report_rewrite_required`: 同じ result で report の説明だけを更新する
- `extra_validation_required`: 同じ仮説と protocol のまま追加 case、figure、集計を行う
- `rerun_required`: protocol または実装を直し、新しい run identity で fresh run を行う
- `approved`: evidence と exit criteria が十分なら loop を閉じる。不十分なら次の変更へ進む

いずれかの rewrite、追加検証、rerun が残る間は結論を閉じません。`approved` は
research claim の受理を意味せず、定めた範囲での次の action が決まったことだけを示します。

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

Run note には、問い・比較・protocol、変更、観測、解釈、limitation、decision、next action と、
commit / run path を必要な範囲で残します。artifact identity と report の構成はそれぞれの
owner に委譲します。

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
