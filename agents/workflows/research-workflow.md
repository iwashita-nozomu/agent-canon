# 研究・実験改造ワークフロー
<!--
@dependency-start
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、数式を伴うアルゴリズム研究、比較実験、段階的なコード改造を 1 つの workflow にまとめた正本です。
対象は、`python/` 配下の実装改造、`experiments/` 配下の比較実験、`notes/` への知見整理を含みます。
準備、実装、静的チェック、実行、結果レポートを通した実務上の統合入口は [experiment-workflow.md](experiment-workflow.md) を参照してください。
この文書は、とくに問い、定式化、比較設計、段階的改造、claim 更新の正本を担います。
批判的レビューの具体的な観点は [experiment-critical-review.md](../../documents/experiment-critical-review.md) を参照してください。

## 1. 目的

- 数式、仮定、比較対象を曖昧なまま実装に入らない
- 各改造の狙いと副作用を、実験前後で比較できる形にする
- 実験コード、result ディレクトリ、report、summary note を一貫した流れでつなぐ
- 途中の思いつきではなく、記録された判断に基づいて順次改造する

## 2. 基本ルール

- 研究目的と benchmark の scope を最初に固定します。目的が曖昧な benchmark は、problem、algorithm、metric、statistics の設計も曖昧になります。
- 実装前に定式化を明文化します。対象の数式、制約、近似、数値法の前提を明記し、どの条件で成り立つかを書きます。
- 比較対象を先に決めます。新手法だけを良く見せる比較ではなく、baseline、広く使われる方法、現時点の有力法を並べます。
- 比較は 1 つの勝者探しより trade-off の把握を重視します。精度、時間、メモリ、頑健性、使いやすさを分けて見ます。
- 実験後の report は、結果の列挙ではなく判断文書として書きます。`Results` と `Discussion` を混同せず、体裁の正本は `documents/experiment-report-style.md` に従います。
- 実装は prototype から始め、少しずつ変更します。大きな改造を 1 回で入れず、各段で test と観測を残します。
- 各結果の provenance を残します。使った code、commit、branch、command、seed、environment、入力条件を追えるようにします。
- run は fresh 実行で完走させます。途中停止 run を resume の正本にせず、停止理由を記録して 0 からやり直します。
- claim は evidence に合わせます。実験範囲を越えた一般化を避け、仮定と限界を本文で明示します。
- correctness evidence と performance evidence を混同しません。正しさの parity test は性能の証拠ではなく、速度比較は数式上の正しさの証拠ではありません。
- runtime success や smoke pass は acceptance の十分条件ではありません。本体実装が `Equation:`、`Assumptions:`、仕様記述、method contract と一致しているかを別に確認します。
- code change、protocol change、XLA / runtime flag change を 1 iteration に混ぜません。1 iteration では 1 種類の変更だけを入れ、差分の原因を追えるようにします。
- user request が generic path の usable smoke を求めている場合、specialized path の tuning や narrow smoke だけで close しません。

## 2.5 Research-Driven Change の canonical loop

外部調査つき実装、性能改善、比較検証では、次の outer loop を正本にします。

1. 問い、比較対象、exit criteria を固定する
1. 外部調査を行い、採用候補と反証候補を残す
1. 比較プロトコルと run layout を固定する
1. baseline または current state を記録する
1. 1 つの code change を入れる
1. 同じ protocol で run する
1. `experiment_reviewer` が evidence sufficiency と overclaim を批判的にレビューする
1. `report_reviewer` が user-facing report をレビューする
1. decision に応じて loop を戻す

decision は次の 4 つに固定します。

- `report_rewrite_required`
  - 同じ result を使って report だけを書き直します
- `extra_validation_required`
  - 同じ仮説のまま追加 case、追加 figure、追加集計を行います
- `rerun_required`
  - fresh `run_name` で rerun します。必要なら code か protocol を修正します
- `approved`
  - exit criteria を満たしていれば loop を閉じます。満たしていなければ次の change を設計します

この loop は 1 回で終える前提にしません。`report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り、結論を閉じることを禁止します。

agent がこの loop を自律実行する場合は、単一 run の実行と rerun 分岐には `agents/skills/experiment-lifecycle.md` を使い、改善 backlog を持つ outer loop には `agents/skills/adaptive-improvement-loop.md` を使います。iteration の記録は `agents/templates/experiment_change_loop.md` を起点にします。

## 3. 文献ベースの要点

以下は外部文献からの要点整理です。

- Sandve らは、各結果がどう生成されたかを追跡し、手作業の data 操作を避け、seed や中間結果も残すことを勧めています。
- Osborne らは、実装前に prototype を作り、logbook を付け、数理・数値法の前提を理解したうえで version control を使うことを勧めています。
- Wilson らは、incremental change、version control、automation、testing、code review を scientific computing の基本としています。
- Weber らは、benchmark は scope、datasets、metrics、parameters、reproducibility を一体で設計し、baseline と neutral comparison を意識すべきだと整理しています。
- Bartz-Beielstein らは、benchmark では goal、problem instance、algorithm instance、performance measure、analysis を先に定義し、問題クラスを越えた一般化に慎重であるべきだと述べています。
- NeurIPS checklist は、claim を実験範囲に合わせ、assumptions と limitations を明示し、再現に必要な code、data、command、environment を示すことを求めています。

## 3.5 参照する外部規範

研究 workflow の review 観点は、少なくとも次を参照します。

- Sandve et al., Ten Simple Rules for Reproducible Computational Research
  - https://doi.org/10.1371/journal.pcbi.1003285
- Wilson et al., Best Practices for Scientific Computing
  - https://doi.org/10.1371/journal.pbio.1001745
- van der Kouwe et al., Benchmarking Crimes
  - https://doi.org/10.48550/arXiv.1801.02381
- ACM Artifact Review and Badging
  - https://www.acm.org/publications/policies/artifact-review-and-badging-current
- FAIR Guiding Principles
  - https://doi.org/10.1038/sdata.2016.18
- NeurIPS Paper Checklist
  - https://nips.cc/public/guides/PaperChecklist
- REFORMS
  - https://reforms.cs.princeton.edu/

これらは同じ観点ではありません。少なくとも次の独立視点として扱います。

- reproducibility
- scientific-computing
- benchmark
- artifact
- fair-data
- ml-science-reporting

## 4. 標準 workflow

### Step 1. 問いを固定する

- `Question:` を 1 文で書きます。
- 何を改善したいのかを、精度、速度、メモリ、安定性、適用範囲のどれかで固定します。
- 「新しい方法を試す」ではなく、「どの failure / bottleneck / claim を検証するか」を書きます。

### Step 2. 定式化を固定する

- `Formulation:` に、問題設定を自然言語で書きます。
- `Equation:` に、対象の式、目的関数、制約、離散化、近似、前処理、停止条件を書きます。
- `Assumptions:` に、成り立ちを支える前提を書きます。
- `Numerical Risks:` に、不安定化、オーバーフロー、近似誤差、conditioning、dtype 依存性を書きます。
- `Equation-to-Code Mapping:` に、どの式、項、constraint、assumption がどの実装 path / function / helper に対応するかを書きます。

### Step 3. 比較設計を固定する

- `Comparison Target:` を先に書きます。
- 比較対象は少なくとも次を含めます。
  - 単純 baseline
  - 現行 main 実装
  - 広く使われる外部法または理論的 reference
- `Metrics:` に、精度、時間、メモリ、失敗率、頑健性などを列挙します。
- `Dataset / Case Range:` に、どの problem class と difficulty range を見るかを書きます。
- `Fairness Notes:` に、parameter tuning、timeout、hardware、seed の公平条件を書きます。
- ordered difficulty 軸は 1 ずつ連続に sweep します。飛び飛びの点だけで frontier や failure onset を判断することを禁止します。
- raw failure count だけで結論を出すことを禁止します。environment noise、case mix、failure kind、success rate を分離してから解釈します。
- failure-onset dimension を記録せずに、implementation bug と真の frontier limit を区別した扱いにすることを禁止します。
- small toy、dense Jacobian、baseline 未比較の結果から trainer replacement、scalability、superiority、広い theorem を主張することを禁止します。

### Step 4. 作業場所と出力先を決める

- branch は既定では分けません。
- 長時間 run の隔離や破壊的な試行が必要な場合に限って、別 branch / worktree の使用を許可します。
- topic README に、`result/<run_name>/` と `experiments/report/<run_name>.md` の置き方を書きます。
- 詳細な作業ログが必要な場合だけ、実験 note か別の補助メモに分けて残します。

### Step 5. prototype を作る

- まず小さい prototype または最小ケースで式と実装の対応を確かめます。
- 可能なら analytical solution、trusted prototype、corner case、旧実装と比較します。
- run が通っても `Equation-to-Code Mapping:` とズレるなら prototype 段階で fail とし、大規模 sweep に進みません。
- prototype 段階で落ちるなら、大規模 sweep に進みません。

### Step 6. 小さく改造する

- 1 commit 1 意図にします。
- 各改造ごとに、次を action log へ残します。
  - `Change:`
  - `Expected Effect:`
  - `Risk:`
  - `Validation Plan:`
- 大きな設計変更は、先に `notes/themes/` または experiment note 側へ意味を書き、あとから code だけが残る状態を避けます。

### Step 7. 各段で検証する

- unit test、small smoke run、reference comparison を段階ごとに実施します。
- bug を直したら、その bug を test に変えます。
- 各段で、runtime 結果とは別に `Equation:`、`Assumptions:`、仕様記述との整合を見直します。式と code のどちらを変えたのか曖昧なまま先へ進みません。
- 主要な比較は次を分けて記録します。
  - correctness
  - numerical stability
  - performance
  - failure pattern

### Step 8. 本 run を 1 回で完走させる

- experiment script は、指定レンジを 1 invocation で完走できるように書きます。
- 途中停止した run は、partial のまま carry-over しません。
- 停止時は `Stop Reason:` と `Restart Decision:` を action log に残し、新しい run_name で fresh run を開始します。

### Step 9. 結果を比較し、claim を更新する

- `Result Summary:` に主要差分を書きます。
- `Interpretation:` に、なぜ差が出たかの読みを書きます。
- `Limitation:` に、今回の範囲で分からないことを書きます。
- 良い結果だけでなく、効かなかった工夫も `Did Not Work:` として残します。
- 実験 note を report として残す場合は、`Abstract`、`Protocol`、`Results`、`Discussion`、`Critical Review` を分けます。

### Step 9.5. 結果を集計し、定量的に読む

- raw JSONL をそのまま読むのではなく、最終判断用の summary table を作ります。
- summary では少なくとも次を分けます。
  - case 数
  - success / failure 数
  - failure kind ごとの件数
  - 主指標の代表値
  - ばらつき
  - baseline 比の差
- figure を使う場合は、軸名、単位、scale、読み取り方を caption か本文に明記します。
- 結論として残す各ポイントには、対応する figure / table を最低 1 つ紐付けます。
- 代表値は平均だけで済ませません。平均、中央値、最小、最大を併記します。四分位や標準偏差が必要な場合は追加します。
- failure を無視した平均だけを出しません。成功率と failure kind を同じ table か同じ section で見えるようにします。
- 比較は絶対値だけでなく、baseline 比、差分、改善率を並べます。
- case mix が変わると数字の意味が崩れるため、比較単位を dimension、level、dtype、problem family などで揃えます。
- 「速くなったが失敗が増えた」「精度は上がったが memory が悪化した」のような trade-off を別指標として切り出します。
- 可能なら、代表例だけでなく worst case、median case、failure case を 1 つずつ本文で確認します。

### Step 10. report をまとめ、summary の要否を決める

- `main` へ戻すときは、code だけでなく test、document、`result/<run_name>/`、`experiments/report/<run_name>.md` を同時に持ち帰ります。
- 複数 run をまたぐ結論だけを `notes/experiments/` にまとめます。
- 判断の流れが必要な場合だけ、`notes/` 側に補助メモとして残します。

## 5. マルチエージェント実験ループ

研究・実験改造では、単発の `design -> implement -> verify` よりも、実験 evidence を挟んだ反復を標準にします。

推奨ループは次です。

1. `manager` が問い、比較対象、終了条件を固定する
1. `researcher` が必要な外部調査を行う
1. `designer` が数式、実装方針、比較プロトコルを定める
1. `experimenter` が baseline または現状 run を実行する
1. `experiment_reviewer` が結果を批判的にレビューする
1. ここから `Research-Driven Change` の loop を開始する
1. `implementer` が 1 つの change を入れる
1. `change_reviewer` が code diff をレビューする
1. `implementer` が review を反映する
1. `experimenter` が同一プロトコルで再実行する
1. `experiment_reviewer` が比較の妥当性と overclaim を再レビューする
1. `experimenter` が user-facing report draft を作る
1. `report_reviewer` が report の概要、主要数値、figure / table、limitations、結論と根拠の対応をレビューする
1. `experimenter` が `report_rewrite_required` を受けた場合、同じ result を使って report を書き直す
1. `experimenter` が `extra_validation_required` を受けた場合、同じ仮説のまま追加検証を行う
1. `implementer` が `rerun_required` または protocol 修正要求を受けた場合、code か protocol を修正して fresh rerun に戻す
1. 両 review が通り、終了条件を満たすまで 6-14 を反復する
1. `final_reviewer` が最終的な claim と diff を独立にレビューする
1. `verifier` が gate を実行する

この loop では、`experimenter` は code を直しません。code を直すのは常に `implementer` です。
逆に、`implementer` は「良さそうに見える結果」を根拠に勝手に claim を広げません。比較の妥当性と解釈の厳しさは `experiment_reviewer` が担い、reader-facing な report の厳しさは `report_reviewer` が担います。
各 `implementer` の change は、別文書の
[implementation-waterfall-workflow.md](implementation-waterfall-workflow.md)
に従う 1 回の waterfall pass として扱います。新仮説や `rerun_required` は、同じ pass 内の横滑りではなく、次 pass の開始条件です。

この loop の内側で、1 回の run、report 生成、rewrite / extra validation / rerun 分岐を扱う実務手順は [experiment-workflow.md](experiment-workflow.md) を正本にします。

## 6. 各プロセスで必須の記録項目

実験 note または worktree action log では、最低でも次のラベルを使います。

- `Question:`
- `Formulation:`
- `Equation:`
- `Equation-to-Code Mapping:`
- `Assumptions:`
- `Comparison Target:`
- `Metrics:`
- `Change:`
- `Expected Effect:`
- `Validation Plan:`
- `Result Summary:`
- `Quantitative Summary:`
- `Comparison Table:`
- `Interpretation:`
- `Critical Review:`
- `Limitation:`
- `Decision:`
- `Next Idea:`
- `Run Reflection:`

`Run Reflection:` には、少なくとも次を書きます。

- どの commit と run directory で検証したか
- どの結果や判断をどこへ反映したか
- 例外的に branch / worktree を使った場合は、その理由と carry-over 方針

agent が反復を自律実行する場合は、これに加えて iteration ごとの `Decision:` と `Next Action:` を `agents/templates/experiment_change_loop.md` に沿って残します。

## 6.5 集計と定量的考察の作法

- `Quantitative Summary:` では、最低でも対象 case 数、成功率、主要 metric の代表値、baseline 差分を出します。
- `Comparison Table:` では、比較対象ごとに同じ case set を並べます。条件が違う列を同じ表に混ぜません。
- `Interpretation:` では、「何がどれだけ変わったか」と「その差にどこまで意味があるか」を分けて書きます。
- report へまとめるときは、`Results` には観測事実を、`Discussion` には説明と比較を置きます。
- 定量的な考察では、次の飛躍を避けます。
  - 平均だけ見て結論を出す
  - 失敗例を除外して改善とみなす
  - 1 つの difficulty 帯の改善を全体改善とみなす
  - speedup を accuracy / robustness の悪化から切り離して語る
  - sample 数が少ないのに強い一般化をする
- case 数が少ない場合や分布が歪む場合は、中央値や rank ベースの比較を優先します。
- 有意差検定を必須にはしませんが、ばらつきが大きいときは effect size、分位点、再現 run の差を少なくとも言葉で扱います。
- 「改善なし」も結果です。改善が見えなかった場合は、その条件帯と failure pattern を残します。

## 6.8 観点別に必要になる補助 workflow

研究 scope が大きい場合は、通常の `Research-Driven Change` loop に加えて次の補助 workflow を使います。

- `reproducibility-hardening`
  - provenance、seed、command、environment、rerunability を固める
- `scientific-computing-hardening`
  - incremental change、testing、automation、prototype discipline を固める
- `benchmark-design-and-fairness`
  - baseline、case mix、measurement rule、confounder を固める
- `artifact-readiness-and-packaging`
  - code、script、raw result、environment、rerun bundle を固める
- `fair-data-packaging`
  - metadata、result path、naming、再利用性を固める
- `ml-science-reporting-checklist`
  - assumptions、limitations、uncertainty、reader-facing reporting を固める

これらは top-level family を増やすのではなく、`Research-Driven Change` の niche workflow として使います。

## 7. 実験コードを書くときのコツ

- 実験コードは「問いと比較」を表現する薄い層に保ちます。case 生成、metric 計算、集計、report 生成は実験コードの責務ですが、process 管理や GPU 割当は runner 側の責務です。
- topic ディレクトリは、少なくとも `README.md`、`cases.py`、`experimentcode.py`、`result/` を意識した構成にします。
- `experimentcode.py` は orchestrator であり、数式や benchmark の意味を隠した巨大 script にしません。比較対象、case range、metric、run_name を読み取れる形にします。
- `cases.py` には case 定義と resource estimate を寄せます。実験意味のある difficulty 設計はここで管理します。
- ordered difficulty 軸は連続レンジを生成します。飛び飛びの点だけを返す helper の使用は debug / smoke 用に限って許可します。
- 実験 README には、問い、比較対象、標準コマンド、`result/<run_name>/` の出力先、`experiments/report/` の入口を書きます。実験者の頭の中にしかない運用を残しません。

### やらないこと

- 実験 script 内で独自の mini-runner を書かない
- 実験 script 内で GPU slot 管理や child process の生存監視をしない
- 実験 script 内で `CUDA_VISIBLE_DEVICES` や `XLA_*` を直接組み立てない
- 実験 script 内で JAX / XLA env を場当たり的に if 文で分岐しない
- 実験 script 内で partial run の resume protocol を作らない
- 実験 script 内で ad hoc な result path 命名や手作業 rename をしない

JAX / XLA env が必要な場合は、shared helper か runtime layer の既存入口を使います。

## 8. Spot Run 禁止

この repo では `spot run` を、事前に固定した比較プロトコルに入っていない一回限りの ad hoc 実行として扱います。

例:

- その場で 1 case だけ回して良い数字だけを見る
- README や note にない条件で単発実行し、その結果を比較根拠に使う
- 途中停止 run の一部 case だけ抜き出して結論に使う
- script を一時編集して手元の都合のよい subset だけ回し、そのまま benchmark evidence として扱う

spot run は次の用途での使用を禁止します。

- 比較表や結論の根拠
- method 採否の判断
- `main` に持ち帰る正式 report の代わり
- review で使う正式 evidence

許されるのは次に限ります。

- local debug
- crash 再現
- import / env / shape mismatch の smoke 確認

この場合も、正式な実験結果と混ぜることを禁止します。debug / smoke として残す場合は `Debug Run:` または `Smoke:` と明記し、research note の主結果へ昇格させません。

## 8.5 考察に対する批判的レビュー

`experiment_reviewer` は、数字そのものだけでなく、数字の読み方を批判的に見ます。
`change_reviewer` と `experiment_reviewer` は、run 完走や metric 改善があっても、数式 / 仕様 / method contract と code がずれていれば accept しません。
最低限の review 観点は [experiment-critical-review.md](../../documents/experiment-critical-review.md) に従います。

最低でも次を確認します。

- 比較対象は十分か
- 同じ case set を比べているか
- failure を都合よく除外していないか
- 代表値の選び方が結論を歪めていないか
- 改善幅は sample 数とばらつきに照らしてどこまで強く言えるか
- 実験コードが equation / assumptions / parameter 記述と一致しているか
- 外部文献との接続が明示されているか
- 結論に必要な data、table、figure が足りているか
- 図の表示方法と scale が妥当か
- 主要な計算式や proof sketch の所在が明示されているか
- 改善した指標の裏で悪化した指標を見落としていないか
- その考察は、観測事実なのか、仮説なのか、推測なのか

review artifact では、次のラベルで切り分けます。

- `Observed:`
- `Supported Interpretation:`
- `Speculative Interpretation:`
- `Missing Evidence:`
- `Overclaim Risk:`

## 9. 比較対象の選び方

- baseline は「弱い相手」ではなく、実務で置き換え候補になるものを選びます。
- 現行 main 実装は必ず比較対象に含めます。
- 新手法を導入する場合は、少なくとも 1 つの単純 baseline と 1 つの強い既存法を入れます。
- 外部比較が難しい場合は、その理由を `Comparison Gap:` として書きます。
- tuning は公平に行います。新実装だけを過度に tuned して既存法を default のままにしません。

## 10. 数式と実装の対応の取り方

- 実装変更ごとに、どの式のどの項をどう変えたかを書きます。
- 実装上の最適化と定式化上の変更を分けて記録します。
- `Equation-to-Code Mapping:` は、少なくとも `式または仕様項目 -> 実装 path -> 近似 / 省略 / guard` の形で残します。
- run が成功しても、mapping が作れない、または mapping 上の意味と code の意味が一致しない場合は、その iteration を accept してはいけません。
- 次の 3 つを区別します。
  - `Mathematical Change:` 問題設定や近似の変更
  - `Numerical Change:` 解法、安定化、dtype、前処理の変更
  - `Implementation Change:` loop、vectorization、memory layout、scheduler の変更
- 比較では、どの層の変更が差を生んだかを混ぜないようにします。

## 11. 生成物と carry-over

- raw JSONL、HTML、SVG、大きい log は `experiments/<topic>/result/<run_name>/` に残します。
- `main` には、完走 run の report と、その意味を説明する要約 note を残します。
- partial run は正本にせず、診断材料としてのみ扱います。
- worktree を閉じる前に、action log を残した場合は `main` から辿れるようにします。

## 12. 推奨ファイル配置

- workflow の正本: `agents/workflows/research-workflow.md`
- report 体裁の正本: `documents/experiment-report-style.md`
- 実験運用規約: `documents/coding-conventions-experiments.md`
- worktree 規約: `documents/worktree-lifecycle.md`
- 1 run の report: `experiments/report/<run_name>.md`
- 実験 note: `notes/experiments/<topic>.md`
- supporting notes: `notes/experiments/<topic>.md` または `notes/themes/<topic>.md`
- 一般化知見: `notes/themes/<topic>.md`

## 13. 参考文献

- Sandve GK, Nekrutenko A, Taylor J, Hovig E. [Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285). PLOS Computational Biology, 2013.
- Osborne JM, Bernabeu MO, Bruna M, et al. [Ten Simple Rules for Effective Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003506). PLOS Computational Biology, 2014.
- Wilson G, Aruliah DA, Brown CT, et al. [Best Practices for Scientific Computing](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1001745). PLOS Biology, 2014.
- Weber LM, Saelens W, Cannoodt R, et al. [Essential guidelines for computational method benchmarking](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-019-1738-8). Genome Biology, 2019.
- Bartz-Beielstein T, Doerr C, van den Berg D, et al. [Benchmarking in Optimization: Best Practice and Open Issues](https://arxiv.org/abs/2007.03488). arXiv, 2020.
- NeurIPS. [Paper Checklist Guidelines](https://nips.cc/public/guides/PaperChecklist).
