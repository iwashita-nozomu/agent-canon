# 実験の標準手順
<!--
@dependency-start
contract workflow
responsibility Documents 実験の標準手順 for this repository.
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、repo 内で実験を進めるときの統合入口です。
個別の `experiments/<topic>/README.md` は、その実験やモジュール固有の使い方として残し、この文書では topic をまたぐ汎用的な実験方法を扱います。

扱う流れは次の 5 段階です。

1. 準備
1. 実験コードの実装
1. 実験コードの静的チェック
1. 実験実行
1. 結果レポート

さらに、実験を進めながらコード自体を改造する必要がある場合は、結果とレポートを毎回生成し、サブエージェントによる批判的レビューを挟んで反復する workflow を標準にします。外部調査つき実装、性能改善、比較検証では、この文書を `Research-Driven Change` の inner loop として使います。outer loop の正本は [research-workflow.md](research-workflow.md) です。

agent がこの反復を自律実行する場合、単一 run と rerun 分岐は `agents/skills/experiment-lifecycle.md`、改善 backlog を持つ継続反復は `agents/skills/adaptive-improvement-loop.md` を入口にします。loop 記録テンプレートは `agents/templates/experiment_change_loop.md` です。

## この文書の読み方

- この文書は、repo 内実験の準備、実装、静的チェック、実行、結果レポートの実務入口を所有します。
- `## 1. この文書の役割` は関連正本への分岐、`## 2. 段階別手順` は実験 run の手順、後半は log-derived 禁止事項、反復 workflow、個別 README、references を扱います。
- experimenter は `## 2. 段階別手順` から topic / run layout を固定し、research-driven task では `research-workflow.md` と合わせて読みます。
- chunked reading では、まずこの map と `## 1. この文書の役割` で責務を確認し、実行段階ごとの subsection だけを開きます。

## 1. この文書の役割

この文書は実験実務の入口です。詳細は次に分けます。

- 問い、定式化、比較設計、claim の更新
  - [research-workflow.md](research-workflow.md)
- 実験コードと生成物の運用規約
  - [coding-conventions-experiments.md](../../documents/coding-conventions-experiments.md)
- レポート本文の構成と figure / table の書き方
  - [experiment-report-style.md](../../documents/experiment-report-style.md)
- 批判的レビューの観点と手順
  - [experiment-critical-review.md](../../documents/experiment-critical-review.md)
- エージェントごとの task workflow
  - [TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)

## 2. 段階別手順

### 1. 準備

実装や run に入る前に、実験名 `<topic>` を固定します。
新規 topic は AgentCanon template path
`vendor/agent-canon/experiments/_template/` を `experiments/<topic>/` へコピーして始めます。

```bash
cp -r vendor/agent-canon/experiments/_template experiments/<topic>
```

コピー後は次の順で編集します。

1. `run.py` の `main::main`
1. `cases.py`
1. `config.yaml`
1. `visualize.ipynb`
1. `README.md`

その後、最低限次を固定します。

- `Question:`
  - 今回の実験で何を確かめたいか。速度、精度、メモリ、failure pattern、安定性のどれが主題か。
- `Comparison Target:`
  - main 実装、旧実装、baseline、外部 reference のどれと比べるか。
- `Metrics:`
  - `summary.json` と report に何を残すか。少なくとも時間、成功率、failure kind、主要誤差を含めます。
- `Stop Condition:`
  - smoke で止めるのか、verified まで進めるのか、正式な比較表や report まで必要なのか。
- `Fairness Notes:`
  - 同じ case set、同じ timeout、同じ hardware、同じ seed policy、同じ allocator 方針をどこまで維持するか。
- `Artifact Plan:`
  - 実験ディレクトリ、`result/<run_name>/` の出力先、`result/<run_name>/logs/` のログ置き場、`experiments/report/<run_name>.md` の置き場、result branch 名を先に固定します。
- `Visualization Plan:`
  - 可視化 notebook を `experiments/<topic>/visualize.ipynb` に置き、読む result artifact と生成する figure / table を先に固定します。Notebook を formal run の起動手順や設定正本にしません。
- `Naming Plan:`
  - topic 名、run_name、result ディレクトリ名、report 名の規則を先に決め、topic README か対応する正本文書へ残します。
- `Registry Plan:`
  - `experiments/registry.toml` の topic entry、canonical entrypoint、formal command、必要なら `active_branch` を先に固定します。
- `Config Snapshot Plan:`
  - checked-in 正本は `experiments/<topic>/config.yaml` に置き、runner が `result/<run_name>/config.json` と `result/<run_name>/config_source.yaml` に残す設定 snapshot の key を固定します。seed、case range、timeout、dtype、backend、worker 数、allocator、feature flag、比較対象を artifact から辿れる形にします。
- `Make Target Plan:`
  - `make experiment-smoke TOPIC=<topic>`、`make experiment-formal TOPIC=<topic>`、または topic 固有 alias を先に固定します。正式 run の exact command を chat や notebook だけに残しません。
- `Execution Plan:`
  - formal run は `main` source checkout で進めます。隔離が必要な実験だけ短期 branch を使い、その場合も生成結果の保存先は専用 result branch にします。
- `Server Run Surface:`
  - main server host で formal run を回す場合、`tools/experiments/run_managed_experiment.py` を使い、`command.json`、`environment.json`、`source_snapshot.json`、`artifact_manifest.json`、`logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log` を topic README の artifact plan に固定します。

次に、隔離の要否を決めます。

- 通常の実験
  - `main` 上で、そのまま進めます。
- 隔離が必要な実験
  - 長時間 run、巨大生成物、破壊的な試行がある場合に限って短期 branch / worktree の使用を許可します。

準備段階で固定する置き場は次です。

- 実験コード
  - `experiments/<topic>/`
- runtime 生成物
  - `experiments/<topic>/result/<run_name>/`
- run-local log
  - `experiments/<topic>/result/<run_name>/logs/`
- 可視化 notebook
  - `experiments/<topic>/visualize.ipynb`
- 1 回の実験 report
  - `experiments/report/<run_name>.md`
- result branch
  - `experiment-results/<topic>` または topic README で固定した専用 branch
- 複数 run をまたぐ要約や知見
  - `notes/experiments/<topic>.md` または `notes/themes/`

top-level の `reports/` は project-wide な review、automation、management report の置き場として扱い、topic ごとの experiment report の正本には使いません。`notes/experiments/` は run ごとの一次 report ではなく、横断的な要約の置き場として使います。

準備段階で固定する命名は次です。

- topic ディレクトリ名
  - `snake_case`
- run_name
  - `<topic>_<variant>_<YYYYMMDDTHHMMSSZ>`
- runtime 生成物
  - `result/<run_name>/summary.json`
  - `result/<run_name>/cases.jsonl`
  - `result/<run_name>/config.json`
  - `result/<run_name>/config_source.yaml`
  - `result/<run_name>/run_manifest.json`
  - `result/<run_name>/eval_manifest.json`
  - `result/<run_name>/artifact_manifest.json`
  - `result/<run_name>/command.json`
  - `result/<run_name>/environment.json`
  - `result/<run_name>/source_snapshot.json`
  - `result/<run_name>/run.log`
  - `result/<run_name>/logs/startup.jsonl`
  - `result/<run_name>/logs/stdout.log`
  - `result/<run_name>/logs/stderr.log`
  - 図を出力する場合は `result/<run_name>/figures/`
- 可視化 notebook
  - `visualize.ipynb`
- report 名
  - `experiments/report/<run_name>.md`

準備段階で確認するものは次です。

- topic の `README.md`
- `experiments/registry.toml`
- 直近の experiment report
- `summary.json` / `cases.jsonl` の schema
- `git status --short`
- 既定の出力先と命名が topic README に書かれているか
- 可視化 notebook の入口と `logs/` の扱いが topic README に書かれているか

`Interpretation:`
準備段階の目的は、今回の run が debug なのか、verified なのか、正式比較なのかを曖昧にしないことです。

### 2. 実験コードの実装

実験コードは、「問いと比較」を表現する薄い層として実装します。
process 管理や GPU 割当は runner 側の責務であり、実験 script 側に重複実装しません。

推奨構成は次です。

- `README.md`
  - 実験目的、コード配置、Make target、YAML config、出力先、可視化 notebook、report の入口、命名規則を書く。
- `cases.py`
  - case 定義、difficulty range、resource estimate を置く。
- `run.py`
  - orchestration と CLI に集中させる。
- `visualize.ipynb`
  - run artifact を読む可視化 notebook を置く。Notebook は説明と図表化を担い、正式 run の起動や test を担いません。
- `result/`
  - `result/<run_name>/` ごとに JSON、JSONL、`logs/`、図を置く。

`experiment_runner` を使う実験で、実験側が実装する対象は次の 5 点に絞ります。

- `task`
  - `task(case, context)` を 1 case の研究ロジックとして実装します。
  - case ごとの結果 record の書き込みは `task` の責務にします。
- `cases`
  - 多重 `for` や直積展開は実験側で終えて、case 列として scheduler に渡します。
- 環境初期化
  - `context_builder(case)` で `TaskContext` を作ります。
  - 必要なら `initializer(context)` を用意し、child の先頭で実行させます。
- ケースごとのリソース推定
  - `resource_estimate(case)` を用意します。
- `SkipController`
  - 起動前 skip が必要なときだけ実装します。

実装時点で、少なくとも次の配置と名前を README に明記します。

- 実験コードの topic パス
- `result/<run_name>/` の canonical 出力先
- `result/<run_name>/logs/` のログ置き場
- `visualize.ipynb` の可視化入口
- `experiments/report/<run_name>.md` の置き場
- 関連する `notes/` を使う場合はその入口
- run_name の形式

`experiment_runner` を使う場合の入口は次です。

- `StandardWorker`
- `StandardFullResourceScheduler`
- `StandardRunner`
- 監視が必要な場合は `RuntimeMonitor`

`experiment_runner` に委譲するものは次です。

- case ごとの fresh child process lifecycle
- timeout と child cleanup
- child / parent の diagnostics 記録
- `ExecutionResult` の completion 管理
- `environment_variables` の child 反映
- GPU / CPU / worker slot の割当
- worker start / finish の host 側観測点

実装時にやらないことは次です。

- 実験 script 内で独自の mini-runner を書く
- 実験 script 内で独自の scheduler を書く
- GPU slot 管理を script 側で持つ
- `CUDA_VISIBLE_DEVICES` や `XLA_*` を script 側で直接組み立てる
- JAX / XLA env が必要な場合に、shared helper や runtime layer を通さず script 側で直書きする
- native crash / signal / timeout の回収を script 側で独自実装する
- `ExecutionResult` 以外の completion 契約を topic 側へ足す
- partial run を前提にした resume protocol を作る
- ad hoc な result path 命名を増やす

### 3. 実験コードの静的チェック

長時間 run の前に、少なくとも静的に次を確認します。

- `pyright`
  - 実験コード、`experiment_runner` 利用部分、集計コードの型整合を確認する。
- `ruff check`
  - import、未使用変数、到達不能コード、雑な例外処理を早めに落とす。
- CLI help
  - `python experiments/<topic>/run.py --help` または topic README で固定した直接入口が通ることを確認する。
- import path
  - top-level import と package path が壊れていないことを確認する。
- 出力 schema
  - `summary.json` に必要な key が揃うよう、集計コードを静的に読んでおく。
- 設定 schema
  - 実験 script が `--config {config_path}` で runner 生成の `config.json` を読めることを確認する。
  - managed runner 経由の `config.json` と `config_source.yaml` から run 条件を復元できることを確認する。

静的チェックの段階では、まだ正式な benchmark conclusion を出しません。
ここでの目的は「長時間 run を始めても、型・import・引数の破綻で止まらない状態」にすることです。

`Note:`
pickle 可否、JAX import 後の env 汚染、GPU visibility の実際の反映は静的チェックだけでは分かりません。
それらは次の実行段階で smoke / verified として確認します。

server 実行の formal run では、`run_manifest.json`、`eval_manifest.json`、`artifact_manifest.json`、`command.json`、`environment.json`、`source_snapshot.json`、`config.json`、`config_source.yaml`、`run.log`、`logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log` が残ることを確認します。
topic 固有の追加ログは `result/<run_name>/logs/` に出ることも確認します。

### 4. 実験実行

実験実行は、少なくとも次の段階に分けます。

#### 4.1 smoke

最小の CPU run か、ごく狭い case range で次を確認します。

- import が通る
- worker が起動する
- JSONL が追記される
- `summary.json` が生成される
- report 再生成の入口が成立する

#### 4.2 verified

本番に近い backend と env で、worker 数を絞って bounded run を行います。
ここで確認するのは次です。

- GPU visibility
- allocator 設定
- worker slot / timeout の挙動
- failure kind の記録
- `summary.json` と `cases.jsonl` の整合

#### 4.3 formal run

比較表や report の根拠にする run は、条件を固定した fresh run として 1 回で完走させます。

- case range
- timeout
- dtype
- platform
- workers per GPU
- allocator 方針
- 出力先
- `config.json` と `config_source.yaml` に固定した設定 snapshot

は run 開始前に固定し、途中で script を書き換えながら継ぎ足しません。

main server host で formal run を回す場合は、次を推奨します。

```bash
make experiment-formal TOPIC=<topic>
```

この Make target は内側で `tools/experiments/run_managed_experiment.py` を呼びます。
wrapper は `experiments/registry.toml` の `formal_inner_command` を見て `result/<run_name>/`、`config.json`、`config_source.yaml`、`command.json`、`environment.json`、`source_snapshot.json`、`run_manifest.json`、`run.log`、`logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log`、`experiments/report/<run_name>.md` の初期 stub をそろえます。
run 終了時に `eval_manifest.json` と `artifact_manifest.json` も更新されます。

formal run の完了後、生成物を source checkout から専用 result branch へ保存します。
checkout は `main` のまま保ち、保存対象は `result/<run_name>/` と
`experiments/report/<run_name>.md` に限定します。

```bash
python3 tools/experiments/publish_result_branch.py \
  --result-dir experiments/<topic>/result/<run_name> \
  --branch experiment-results/<topic>
```

remote にも保持する正式 run では `--push` を足します。
この tool は `run_manifest.json` の source branch と current checkout が `main`
で一致することを確認してから result branch を更新します。

#### 4.4 long run のルール

- 長時間 run でも、別 branch / worktree は必須ではありません。隔離が必要なときだけ使います。
- run は 1 つの run_name と 1 つの出力先に閉じた fresh 実行として扱います。
- case ごとの JSONL は progress 記録と failure 診断のために保存します。
- partial run の保存は診断材料に限って許可します。正規の再開点としての使用を禁止します。
- 止まった run は `Stop Reason:` と `Restart Decision:` を log に残し、新しい run_name で 0 からやり直します。

#### 4.5 monitor

host 側で worker 状態や GPU 利用状況を見たい場合は、`RuntimeMonitor` を使います。
ただし monitor は evidence そのものではなく、run の観測補助です。
正式な evidence は最終的に JSON、JSONL、report、note へ落とします。

### 5. 結果レポート

run 後は、必ず結果を report と note に整理します。
批判的レビューの観点は [experiment-critical-review.md](../../documents/experiment-critical-review.md) を正本にします。
user-facing report の体裁と根拠導線は [experiment-report-style.md](../../documents/experiment-report-style.md) を正本にし、`report_reviewer` の独立レビューを必須にします。

最低限残すものは次です。

- `summary.json`
- `cases.jsonl`
- `config.json`
- `config_source.yaml`
- `run_manifest.json`
- `eval_manifest.json`
- `artifact_manifest.json`
- `command.json`
- `environment.json`
- `source_snapshot.json`
- `run.log`
- `logs/startup.jsonl`
- `logs/stdout.log`
- `logs/stderr.log`
- `visualize.ipynb`
- report へのリンク
- `Result Summary:`
- `Quantitative Summary:`
- `Comparison Table:`
- `Critical Review:`
- `Report Review:`

report 本文は次の構成を基本にします。

- `Question and Context`
- `Protocol`
- `Results`
- `Discussion`
- `Limitations`
- `Reproducibility Record`
- `Artifacts and Carry-Over`
- `Critical Review`
- `Conclusion`

結果レポートでは、少なくとも次を分けます。

- 観測事実
  - `Results`
- その意味と比較
  - `Discussion`
- まだ言えないこと
  - `Limitations` と `Critical Review`

carry-over のルールは次です。

- 実行ごとの生成物は `experiments/<topic>/result/<run_name>/` に残す
- 実行ごとの追加ログは `experiments/<topic>/result/<run_name>/logs/` に残す
- 可視化 notebook は `experiments/<topic>/visualize.ipynb` に残し、run artifact を読む形にする
- 1 回の実験 report は `experiments/report/<run_name>.md` に残す
- formal run の生成物は `tools/experiments/publish_result_branch.py` で専用 result branch に保存する
- 複数 run をまたぐ知見だけを `notes/` へ持ち上げる
- partial run は診断用とし、正式な report の正本にしない

## 2.5 Log-Derived Prohibitions

repo と対応する worktree logs から抽出した再発防止事項を、実験・性能改善の固定 gate として扱います。

- spot run、debug run、smoke run、partial run を正式 evidence にしません。
- correctness evidence と performance evidence を混同しません。
- raw failure count だけで結論を出しません。environment noise、case mix、failure kind、success rate を分離します。
- code change、protocol change、XLA / runtime flag change を 1 iteration に混ぜません。
- user request が generic path の usable smoke を求めている場合、specialized path の tuning や bounded smoke だけで完了扱いにしません。
- scope で禁止された runner 変更、function fusion、別経路追加を性能改善のついでに入れません。
- failure-onset dimension を残さず、implementation bug と真の frontier limit を混同しません。
- toy-only、dense Jacobian、baseline 未比較の結果から trainer replacement、scalability、superiority、広い theorem を主張しません。
- 理論 note が一般 weighted case の正しい抽象でないと示した unrestricted permutation-group enumeration を継続投資対象にしません。

## 3. コード改造を伴う反復ワークフロー

実験を行いながらコードを改造する必要がある場合は、単発の

- 実装
- 実行
- 感想

では終わらせず、毎回の実験で結果とレポートを生成し、サブエージェントによる批判的レビューを挟んで反復します。

標準ループは次です。

1. `manager`
   - 今回の `Question:`、`Comparison Target:`、`Stop Condition:` を固定する。
1. `implementer`
   - コード変更を入れる。
1. `change_reviewer`
   - code diff を批判的にレビューする。
   - 数学的妥当性や報告内容も確認する場合は [experiment-critical-review.md](../../documents/experiment-critical-review.md) の `Mathematical Validity` と `As Reported` を使う。
1. `implementer`
   - review を反映し、静的チェックを通す。
1. `experimenter`
   - 同じ protocol で fresh run を実行する。
1. `experimenter`
   - `summary.json`、`cases.jsonl`、draft report を生成する。`notes/` を使う場合は対応する experiment note も生成する。
1. `experiment_reviewer`
   - report と結果の読み方を批判的にレビューする。
   - [experiment-critical-review.md](../../documents/experiment-critical-review.md) を使って、math validity、evidence sufficiency、figure validity、overclaim を確認する。
1. `report_reviewer`
   - user-facing report を独立にレビューする。
   - 実験の概要、主要数値、figure / table、結論と根拠の対応、limitations を確認する。
   - review outcome を `report_rewrite_required`、`extra_validation_required`、`rerun_required`、`approved` のいずれかで返す。
1. `experimenter`
   - `report_rewrite_required` の場合、同じ result を使って report を書き直す。

この反復を agent が自律実行する場合は、1 iteration ごとに `Change:`、`Validation Plan:`、`Run Name / Path:`、`Decision:`、`Next Action:` を `agents/templates/experiment_change_loop.md` に記録します。
   - `extra_validation_required` の場合、同じ比較方針で追加検証を行う。
   - `rerun_required` の場合、新しい run_name で fresh rerun を行う。
1. `implementer`
   - code や protocol の修正が必要な場合だけ修正を入れる。
1. 4-10 を終了条件まで反復する。
1. `final_reviewer`
   - 最終 code と最終 claim を独立にレビューする。
1. `verifier`
   - gate を実行する。

この workflow の要点は次です。

- repo に持ち帰る各 code change は [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md) の 1 pass として扱う
- 毎回の実験で、結果とレポートを必ず生成する
- code review と report review を分ける
- `experiment_reviewer` と `report_reviewer` を分ける
- 同じ protocol で再実行し、都合のよい subset に逃げない
- 修正のたびに静的チェックを挟む
- 良い結果だけでなく、失敗例、悪化例、未解決点も同じ note に残す
- report review の outcome を `rewrite`、`extra validation`、`rerun` のどれかに明示する
- 対処順は `rerun` → `extra validation` → `rewrite` → `approved` に固定する

### 3.1 各サイクルで必ず残すもの

各 iteration で最低限残すものは次です。

- `Change:`
- `Expected Effect:`
- `Validation Plan:`
- 静的チェック結果
- 実行コマンド
- `result/<run_name>/` の所在
- `result/<run_name>/logs/` の所在
- 可視化 notebook の所在
- `config.json` と `config_source.yaml` の所在と主要 key
- `command.json`、`environment.json`、`source_snapshot.json`、`artifact_manifest.json` の所在
- report の所在
- 置き場と命名規則の変更有無
- `Critical Review:`
- `Report Review:`
- `Decision:`
- `Next Idea:`

### 3.2 反復を止めてよい条件

反復は、少なくとも次のどれかを満たしたときに止めます。

- 事前に決めた `Stop Condition:` を満たした
- 追加変更を入れても改善が見えず、`Critical Review:` でそれを説明できる
- fairness を保った比較で、現時点の claim と limitation が十分に整理できた
- それ以上の実験が、別 topic や別 branch に分けるべき新しい問いへ変わった

## 4. 個別 README の位置づけ

`experiments/<topic>/README.md` は引き続き必要です。
ただし、役割はこの文書と分けます。

- この文書
  - 実験全般の標準手順
- topic README
  - その実験固有の目的、入力、CLI、可視化 notebook、`result/<run_name>/` と `logs/` の置き場、`experiments/report/<run_name>.md` の置き場、run_name 規則、既知の注意点

個別 README は「そのモジュールや実験をどう使うか」を書き、
この文書は「repo で実験をどう進めるか」を書く、という分担にします。

## 5. References

ローカルの入口は次です。

- [references/README.md](../../references/README.md)
- [workflow-references.md](workflow-references.md)

### 実験手順・再現性

- [Sandve et al. (2013), Ten Simple Rules for Reproducible Computational Research](https://doi.org/10.1371/journal.pcbi.1003285)
- [Wilson et al. (2014), Best Practices for Scientific Computing](https://doi.org/10.1371/journal.pbio.1001745)
- [Wilson et al. (2017), Good Enough Practices in Scientific Computing](https://doi.org/10.1371/journal.pcbi.1005510)
- [Nature, Guidance on Reproducibility for Papers Using Computational Tools](https://www.nature.com/articles/d41586-022-00563-z)
- [Bartz-Beielstein et al. (2020), Benchmarking in Optimization: Best Practice and Open Issues](https://doi.org/10.48550/arXiv.2007.03488)

### 批判的レビュー・図表

- [Minocher et al. (2023), Implementing Code Review in the Scientific Workflow](https://doi.org/10.12688/f1000research.27137.2)
- Tiwari et al. (2021), Reproducibility in Systems Biology Modelling
- [Rougier et al. (2014), Ten Simple Rules for Better Figures](https://doi.org/10.1371/journal.pcbi.1003833)

### 生成AIの活用

- Rethinking the AI Scientist: Interactive Multi-Agent Workflows for Scientific Discovery
- Towards Scientific Discovery with Generative AI: Progress, Opportunities and Challenges
- Wu et al. (2025), Automated Literature Research and Review-Generation Method Based on Large Language Models
- OpenReviewer: A Specialized Large Language Model for Generating Critical Scientific Paper Reviews

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
