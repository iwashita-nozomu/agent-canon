# 実験レポートの書き方

この文書は、`experiments/report/` に残す実験レポートを、学術的な report に近い体裁で書くための正本です。
対象は、`experiments/` 配下の比較実験、benchmark、アルゴリズム改造後の検証レポートです。
human-readable な experiment report の正本は `experiments/report/` とし、render された HTML / SVG や JSON / JSONL / log は `experiments/<topic>/result/<run_name>/` に置きます。top-level の `reports/` は project-wide な review や automation report の置き場であり、topic ごとの experiment report の正本にはしません。

repo 固有の結論を先に言うと、実験レポートは IMRaD をそのまま縮小再現するのではなく、次の `IMRaD+` で書くのがよいです。

1. `Title`
1. `Abstract`
1. `Question and Context`
1. `Protocol`
1. `Results`
1. `Discussion`
1. `Limitations`
1. `Reproducibility Record`
1. `Artifacts and Carry-Over`
1. `Critical Review`

これは外部の学術 writing guide を、この repo の `experiments/` と `notes/` の運用に合わせて再構成したものです。以下の「carry-over」や `summary.json` の扱いなどは repo 向けの推論です。

## 1. 基本方針

- レポートは「実行ログ」ではなく「読んで判断できる文書」として書きます。
- `Results` では、まず観測事実を出します。`Discussion` では、その意味を解釈します。
- `Abstract` は最初に置きますが、最後に書きます。
- 表と図は、本文に埋め込まれた補助資料ではなく、単体でも読める evidence として扱います。
- 各 figure には、軸名、単位、scale、読み取り方を最低 1 文で添えます。
- headline metric だけでなく、case 数、成功率、failure kind、ばらつき、比較条件を同時に示します。
- 良い結果だけを report せず、negative result、unexpected result、limitations も同じ文書に残します。
- 結論節では、根拠になった図表番号を明示して、結論と evidence の対応を切らさないようにします。
- `experiments/report/<run_name>.md` は、`experiment_reviewer` と独立した `report_reviewer` の両方を通すまで draft 扱いにします。

## 2. 標準構成

## 2.0 置き場

- experiment report の Markdown 正本は `experiments/report/<run_name>.md` を既定にします。
- 対応する機械生成物は `experiments/<topic>/result/<run_name>/` に置きます。
- report 本文からは、少なくとも `eval_manifest.json`、`summary.json`、`cases.jsonl`、主要な図やログを辿れるようにします。
- 複数 run をまたぐ考察は `notes/experiments/` や `notes/themes/` に分けます。

## 2.1 Title

- title は topic-first にしつつ、比較対象と主要結論が分かる形にします。
- vague な題名や疑問文を避けます。
- 実験レポートでは、少なくとも次の 2 つのうち 1 つを入れます。
  - 比較対象
  - 主たる結果

例:

- `Smolyak Integrator: Initialization Cost Still Dominates at Medium Levels`
- `Experiment Runner Hardening: Timeout and Live Capacity Reduce Hung-Run Risk`

## 2.2 Abstract

- `Abstract` は 4-7 文を目安にします。
- Abstract は最後に書きます。
- 1 文ずつ役割を分けると書きやすいです。
  - 問い
  - 実験条件 / 方法
  - 最も重要な結果
  - その意味
  - limitation または scope
- 抽象的な「改善した」だけで終わらせず、最重要の数字を 1 つ以上入れます。

最低限含めるもの:

- `Question:`
- 比較対象
- case 範囲または protocol の要約
- strongest result with numbers
- limitation または適用範囲

## 2.3 Question and Context

- なぜこの実験が必要かを短く書きます。
- 先行結果、main 実装、baseline のどこに gap があるかを示します。
- ここで長い action log を再掲しません。問いと比較対象に集中します。

最低限含めるもの:

- `Question:`
- `Formulation:`
- `Comparison Target:`
- `Metrics:`

## 2.4 Protocol

- `Methods` というより、この repo では `Protocol` と書く方が実態に合います。
- 再現に必要な情報を、後から実行できる粒度で書きます。
- 実験条件の公平性をここで固定します。

最低限含めるもの:

- 実行コマンド
- branch / commit / worktree
- hardware
- software / runtime version
- case range
- sweep order
- timeout
- seeds
- fairness notes
- `summary.json` / `cases.jsonl` の生成手順

`Protocol` に入れるが `Results` へ混ぜないもの:

- JAX / CUDA / Python version
- allocator 設定
- timeout 条件
- hardware topology
- aggregation rule

## 2.5 Results

- `Results` は観測したことを系統立てて report します。
- ここでは「何が起きたか」を書き、「なぜ起きたか」は `Discussion` へ回します。
- 図表を出すときは、本文で先にその図表が何を示すかを 1 文で述べます。

書き方の順序:

1. 主結果を 1 文で出す
1. その主結果を supporting data で支える
1. secondary trend が主結果の解釈に必要な場合は述べる
1. 例外や unexpected outcome を述べる

`Results` で必ず見えるようにするもの:

- case 数
- success / failure 数
- failure kind ごとの件数
- 主要 metric の代表値
- baseline 比較
- 例外ケース
- 主張の根拠となる figure / table 番号

避けること:

- 結論や原因推定を先に書く
- failure を落として平均だけ出す
- 図表を貼るだけで本文に主要 trend を書かない

## 2.6 Discussion

- `Discussion` は、結果の意味、先行研究や baseline との関係、設計上の含意を書く section です。
- ここで初めて explanation や speculation を扱います。
- ただし、新しい未提示データは入れません。

順序の目安:

1. principal finding を言い直す
1. 仮説または問いに照らして解釈する
1. baseline / prior result と比較する
1. unexpected outcome を説明する
1. take-away を 1 つに絞る

repo では、次のラベルで observation と interpretation を分けると読みやすいです。

- `Observed:`
- `Supported Interpretation:`
- `Speculative Interpretation:`

## 2.7 Limitations

- limitation は「弱気の謝罪」ではなく、claim の有効範囲を明示する section です。
- 少なくとも次を確認します。
  - case range は十分か
  - hardware dependency は強いか
  - failure case を十分説明したか
  - sample 数や trial 数は足りているか
  - comparison gap は残っていないか

## 2.8 Reproducibility Record

- 計算実験では、再現情報を report の一部として明示します。
- 既に `summary.json` に入っている情報でも、本文から辿れるように要約を書きます。

最低限含めるもの:

- branch
- commit
- worktree
- command
- hardware
- software versions
- seeds
- timeout
- output paths

## 2.9 Artifacts and Carry-Over

- `main` 側 note は raw 結果置き場ではないので、artifact への入口を整理します。
- この section では次を分けます。
  - raw JSONL
  - `summary.json`
  - plots / HTML report
  - `main` に持ち帰るもの

## 2.10 Critical Review

- 最後に、自分たちの読みを疑う section を置きます。
- これは `Discussion` の繰り返しではなく、「この report がまだ主張していないこと」を明示する section です。
- 詳細な review 観点は [experiment-critical-review.md](experiment-critical-review.md) を参照してください。

最低限含めるもの:

- `Mathematical Validity:`
- `Literature Connection:`
- `Evidence Sufficiency:`
- `Figure Validity:`
- `Equation Visibility:`
- `Overclaim Risk:`
- `Missing Evidence:`
- `Alternative Explanation:`
- `Next Check:`

少なくとも次は reviewer が確認します。

- 実験コードが本文の数式、仮定、protocol と一致しているか
- report が結果の羅列ではなく、問いに対する判断文書になっているか
- 外部文献や baseline との接続が明記されているか
- 結論を支えるデータ、case 数、failure kind、table / figure が足りているか
- 図の表示方法が誤解を招かないか
- 主要な計算式、変数、仮定が読者に見えるか

## 2.11 Report Review Gate

- user-facing report は、`report_reviewer` による独立レビューを必須にします。
- `report_reviewer` は少なくとも次を確認します。
  - 実験の概要、問い、比較対象、protocol が冒頭で分かるか
  - `Abstract` が strongest result を numbers つきで述べるか
  - headline metric の近くに case 数、success / failure、failure kind があるか
  - 各 major claim が figure または table を参照しているか
  - figure / table が単体で読めるか
  - `Results` と `Discussion` が分かれているか
  - limitations と missing evidence が report 内に明示されているか
- review outcome は次の 4 つに固定します。
  - `approved`
  - `report_rewrite_required`
  - `extra_validation_required`
  - `rerun_required`
- `report_rewrite_required` の場合だけ、同じ result を使った report の書き直しで閉じてよいです。
- `extra_validation_required` と `rerun_required` の場合は、report を閉じずに実験 workflow へ戻ります。
- 対処順は次に固定します。
  - `rerun_required`
  - `extra_validation_required`
  - `report_rewrite_required`
  - `approved`

## 3. 図表の扱い

- 表は exact numbers に向きます。
- 図は trend, frontier, distribution, trade-off の把握に向きます。
- 図表番号は本文の登場順に振ります。
- caption は「何を見ればよいか」が分かる self-contained な説明にします。
- figure caption は、可能なら最初の 1 文を結論文にします。
- すべての軸に名前を付け、可能なら単位も書きます。
- 軸 scale が linear か log かを、軸ラベルまたは caption のどちらかで明示します。
- 読み手が迷いやすい図では、caption か本文冒頭に `How to read:` を 1 文入れます。
- 1 つの figure で複数 series を見せるときは、何を比べればよいかを caption に書きます。
- 結論や本文の主張から figure を参照するときは、`Figure 2 shows ...` のように evidence を明示します。

良い caption の最小形:

1. 何を比較しているか
1. どの条件か
1. 主要 trend は何か
1. 例外条件があるか

### 3.1 線形軸と対数軸

- 線形軸は、差分そのものを読みたいときに使います。
- 対数軸は、桁差、比率、指数的増加、heavy tail を見たいときに使います。
- 0 や負値を含む指標に、理由なく log 軸を使いません。
- log 軸を使うときは、caption や本文で「比率を見るため」「桁差を見るため」と理由を 1 文で書きます。
- linear 軸のままだと先頭の小さい値が潰れる場合だけ、安易ではなく意図を持って log 軸へ切り替えます。
- 同じ report 内で linear / log を混在させるときは、図ごとに scale を明示します。

### 3.2 結論と図表の対応

- `Conclusion` や `Discussion` で主張する各ポイントには、根拠図または根拠表を最低 1 つ紐付けます。
- figure を貼るだけで終わらせず、本文で「この主張は Figure N と Table M に基づく」と書きます。
- 強い主張ほど、単一図ではなく summary table と representative figure の両方で支えます。
- failure pattern や limitation を述べるときも、それを示す figure / table をできるだけ添えます。

## 3.3 sweep 設計

- 次元、level、problem size のような ordered difficulty 軸は 1 ずつ連続に上げます。
- `1, 4, 8, 16` のような飛び飛びの点だけで結論を作りません。
- coarse sweep を使うのは、debug、smoke、予備探索、またはコスト制約が強い場合に限ります。
- 飛び飛びの sweep を採用する場合は、`Protocol` に理由を書き、結論の強さも下げます。
- contiguous sweep にする理由は、frontier、急な崩れ、failure onset、非単調性を見落としにくくするためです。

## 4. repo 用の推奨見出し

`experiments/report/` では、次の見出しを推奨します。

    # <Topic-First Title>

    ## Abstract

    ## Question and Context

    ### Question
    ### Formulation
    ### Comparison Target
    ### Metrics

    ## Protocol

    ## Results

    ### Quantitative Summary
    ### Comparison Table
    ### Main Trends
    ### Exceptions and Failures

    ## Discussion

    ### Supported Interpretation
    ### Comparison with Baseline or Prior Work
    ### Speculative Interpretation

    ## Limitations

    ## Reproducibility Record

    ## Artifacts and Carry-Over

    ## Critical Review

## 5. 実験ログとの違い

- `experiment_log.md` は run-centered です。
- experiment report は reader-centered です。
- log では時系列を残します。
- report では問い、結果、解釈、限界、artifact を整理します。

したがって、実験後は `experiment_log.md` をそのまま正本にせず、report へ再構成します。

## 6. 参考にしたソース

以下を参考にしました。repo 固有の `IMRaD+` 構成や `carry-over` 節は、これらをこの repo に合わせて再構成したものです。

ローカルの入口は次です。

- [references/README.md](/mnt/l/workspace/project_template/references/README.md)
- [workflow-references.md](/mnt/l/workspace/project_template/agents/workflows/workflow-references.md)

- George Mason University Writing Center, [Writing an IMRaD Report](https://www.stat.cmu.edu/~brian/valerie/617-2022/week01/imrad%20advice/Writing_an_IMRAD_report.pdf)
- George Mason University Writing Center, [Scientific (IMRaD) Research Reports — Results and Discussion Section](https://writingcenter.gmu.edu/writing-resources/imrad/imrad-results-discussion)
- Mississippi University for Women, [Writing Style for Research Reports](https://www.muw.edu/scimath/writing/reports/)
- PLOS, [How to Write Discussions and Conclusions](https://plos.org/resource/how-to-write-conclusions/)
- [Nature, Guidance on Reproducibility for Papers Using Computational Tools](https://www.nature.com/articles/d41586-022-00563-z)
- [Rougier et al., Ten Simple Rules for Better Figures](https://doi.org/10.1371/journal.pcbi.1003833)
- [NeurIPS, Paper Checklist Guidelines](https://nips.cc/public/guides/PaperChecklist)
- Tiwari et al., Reproducibility in Systems Biology Modelling
- EQUATOR Network, [Reporting guidelines and journals: fact & fiction](https://www.equator-network.org/toolkits/using-guidelines-in-journals/reporting-guidelines-and-journals-fact-fiction/)
