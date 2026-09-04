# research-workflow
<!--
@dependency-start
contract skill
responsibility Owns research-driven change: external evidence, comparison design, claim scope, and the post-run decision loop.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/algorithm-implementation-boundary.md equation-to-code boundary policy
upstream design ../../documents/experiments/experiment-critical-review.md critical evidence review
downstream skill literature-survey source search and source packet owner
downstream skill experiment-lifecycle single-run and rerun owner
downstream skill adaptive-improvement-loop backlog-driven iteration owner
@dependency-end
-->

## Reader Map

- Scope: research questions, external evidence, comparison design, and claims
  that are updated from experiment or implementation evidence.
- Use When: an implementation, benchmark, or design change needs prior-art
  evidence or a claim bounded by an explicit comparison.
- Section path: `Research Contract` fixes the question and evidence boundary;
  `Canonical Loop` governs the outer iteration; `Evidence Reading` controls
  quantitative interpretation; `Boundary` routes runs, sources, and reports.

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

## Research Contract

実装や正式な run の前に、次の contract を一つの task artifact、design brief、または
experiment note に固定します。ここでは実験の合否を先に決めず、結果を解釈するための
問いと観測範囲を定めます。

- `Question:` 何を確かめるかを一文で書く
- `Scope:` problem class、dataset/case range、hardware、適用外条件を固定する
- `Formulation:` 問題設定、数式、制約、近似、停止条件、前提を明記する
- `Equation-to-Code Mapping:` 式、項、constraint、assumption、state boundary と
  実装 path / symbol の対応を記録する（数値問題では
  `algorithm-implementation-boundary.md` の map を使う）
- `Comparison Target:` baseline、current implementation、妥当な外部 reference を
  選び、比較しない候補と理由も残す
- `Metrics:` correctness、numerical stability、performance、failure pattern を
  分けて定義する
- `Dataset / Case Range:` ordered difficulty は連続した範囲を指定する
- `Fairness Notes:` tuning、timeout、hardware、seed、case set を比較間で揃える
- `Evidence Targets:` 何を観測すれば claim を限定的に支持できるかを書く
- `Protocol:` run command、入力、設定、seed、出力先、fresh-run 方針を固定する
- `Operational Stop Condition:` resource、時間、障害時の停止条件を定める

計画に `supported`、`rejected`、`inconclusive`、`approved` を成功条件として置きません。
それらは run 後の解釈または iteration 遷移にだけ使います。runtime success、smoke pass、
parity test、速度差は、それぞれ研究上の結論を直接意味しません。

## Canonical Loop

1. `Question`、`Scope`、`Comparison Target`、`Evidence Targets`、`Protocol`、
   `Operational Stop Condition` を固定する
1. `$literature-survey` が作成した source packet を受け取り、採用された source claim と
   この task の claim の対応を固定する。source の検索、URL / DOI、access date、cache、
   採否の記録は `$literature-survey` に残し、research 側で source record を複製しない
1. baseline または current state を同じ protocol で記録する
1. 一つの code change、protocol change、または runtime change だけを選ぶ。同じ
   iteration に複数種類を混ぜない
1. `experiment-lifecycle` で fresh run を実行し、source、command、環境、seed、結果の
   provenance を記録する
1. `experiment-review` で比較の妥当性、数式・仕様との一致、overclaim、trade-off を
   見る。reader-facing report が必要なら `report-writing` を追加する
1. run 後の decision に応じて戻り先を決める

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
- raw failure count だけで判断せず、case mix、failure kind、success rate、environment
  noise、failure-onset dimension を分ける
- 平均だけでなく中央値、最小、最大、必要なら分位点やばらつきを比較し、同じ case set と
  denominator を使う
- 改善した指標の背後にある悪化（速度と失敗率、精度と memory など）を同じ record に残す
- toy-only、baseline 未比較、一つの difficulty 帯だけの結果から scalability、superiority、
  trainer replacement、広い theorem を主張しない
- `Results` は観測、`Discussion` は解釈、`Limitations` は言えない範囲として分ける
- claim は source と artifact に辿れるようにし、推測を観測事実として書かない

## Research Records

必要な段階だけ、次のラベルを task artifact または note に残します。

`Question:`、`Formulation:`、`Equation:`、`Equation-to-Code Mapping:`、`Assumptions:`、
`Comparison Target:`、`Metrics:`、`Dataset / Case Range:`、`Fairness Notes:`、
`Evidence Targets:`、`Protocol:`、`Change:`、`Expected Effect:`、`Validation Plan:`、
`Risk:`、`Result Summary:`、`Quantitative Summary:`、`Comparison Table:`、
`Interpretation:`、`Critical Review:`、`Limitation:`、`Decision:`、`Next Idea:`、
`Run Reflection:`、`Next Action:`。

`Run Reflection:` には、使用した commit と run path、反映先、次に再利用できる観測、
および例外的な branch / worktree の理由を記録します。`Critical Review:` は観測と
解釈の対応、比較の妥当性、overclaim、未解決 evidence を要約します。review の実行手順、
artifact の role・checksum・readback、reader-facing report の構成は、それぞれ
`experiment-review`、`result-artifact-writeout`、`report-writing` に委譲します。

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

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/research-workflow.md`.
1. Fix the question, scope, comparison target, evidence targets, protocol, and operational stop condition before implementation or formal execution.
1. Do not use research acceptance states as plan-time run or completion gates; record them only after evidence exists.
1. Invoke `$literature-survey` before external search when a source-backed claim, method comparison, or benchmark premise is in scope.
1. Use `$experiment-lifecycle` for one run or fresh rerun and `$adaptive-improvement-loop` for a backlog-driven sequence of changes.
1. Keep code, protocol, and runtime changes separate within one iteration and preserve provenance for the source, command, environment, seed, and run identity.
1. Separate correctness, numerical stability, performance, and failure-pattern evidence; do not infer a research claim from smoke success, parity, total time, or raw failure count alone.
1. Review observed facts, supported interpretation, speculation, missing evidence, overclaim risk, and limitations as separate items.
1. Close only when the selected post-run decision is resolved and the claim remains within the recorded scope; otherwise return to the indicated loop state.
