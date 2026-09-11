<!--
@dependency-start
contract template
responsibility Provides the canonical planning and provenance README for an experiment topic.
upstream design ../../../documents/experiments/README.md experiment directory and registry route.
upstream design ../../../documents/design/experiment-topic-template.md single-source topic scaffold and result layout.
upstream design ../../../documents/operations/annex.md pointer/payload boundary and native annex operation readback.
upstream implementation ../../../tools/experiments/artifacts/save_experiment_result_annex.py explicit raw retention owner.
downstream implementation ./provenance.toml records machine-readable plan and provenance.
downstream implementation ./run.py provides the runnable topic scaffold and atomic summary publication.
downstream implementation ../../../tools/experiments/lifecycle/create_experiment_topic.py materializes this topic pair.
@dependency-end
-->

# <Experiment topic>

この文書は、実験の問い、仮説、比較対象、topic 固有の評価・観測、資源選定、結果 provenance を一つの
topic record に整理します。評価指標、比較方法、研究上の成功判断は topic / research owner が定義し、
共通 scaffold は run identity、artifact path、terminal / failure state、provenance / readback の運用だけを
提供します。実験コードの共通 scaffold はこの directory の `run.py`、`cases.py`、
`visualization.py` を利用し、topic 固有の algorithm と renderer はこの topic 内で実装します。

## Reader Map

実験開始前に question → hypothesis → cases/observables → resource/env → managed run → result/failure
の順で確認します。実験毎の計画と machine-readable な値は `provenance.toml` に記録します。

- `.gitignore`: topic-local raw input、raw output、中間物を通常 Git blob から除外する境界。
- `README.md`: 人間向けの計画、判断、再現手順。
- `provenance.toml`: 実験計画・resource・run・result の機械可読な provenance。
- `run.py`: managed runner の入口、case 集約、schema、atomic publication、manifest readback。
- `cases.py`: `CaseSpec`、`CaseResult`、case registry、worker、failure classification。
- `visualization.py`: 可視化 status と topic 固有 renderer の唯一の拡張点。既定では notebook を生成しない。
- `config.yaml`: topic 固有の実験設定。
- `report/`: 人間向けの report 出力領域。
- `result/`: run ごとの機械生成結果領域。大規模な保持物は契約に従って annex へ移送する。

pointer/payload の境界と native annex 操作の正本は
[documents/operations/annex.md](../../documents/operations/annex.md) です。この README は
topic に固有の適用だけを定め、annex の全体規約を複製しません。`result/<run-id>/summary/`
などの Git pointer/metadata と、外部 annex worktree に保持する payload は別々に読み戻します。

## Topic files

```text
experiments/<topic>/
├── .gitignore
├── README.md
├── provenance.toml
├── run.py
├── cases.py
├── visualization.py
├── config.yaml
├── report/
│   └── .gitkeep
└── result/
    └── .gitkeep
```

## 実行契約

topic は `tools/experiments/execution/run_managed_experiment.py` から呼び出します。topic の `run.py` を
直接起動せず、caller が `EXPERIMENT_RUN_DIR`、`EXPERIMENT_RUN_MANIFEST`、
`EXPERIMENT_VARIANT` を設定した managed route を使います。

一回の結果は `result/<run-id>/` に作成し、生結果と要約を必ず次の二つへ分けます。

```text
result/<run-id>/
├── raw/                         # case worker が生成する生結果; 通常 Git では ignore
└── summary/                     # runner が atomic に公開する compact 要約・証跡
    ├── summary.json
    ├── cases.jsonl
    ├── artifact-manifest.json
    ├── config_snapshot.json
    ├── provenance_snapshot.toml
    ├── environment.json
    ├── visualization-status.json
    └── failure-evidence.json     # failure/incomplete のとき
```

`summary/summary.json` と `summary/cases.jsonl` が canonical path です。run root に同名の
fallback を作成しません。case worker へ渡す出力先は `EXPERIMENT_RAW_DIR` または runner が
解決した `raw/` です。summary の各 file は atomic replacement と readback digest を通して
公開します。

## 計画・実行・結果解釈の境界

- `provenance.toml` の plan は question、hypothesis、cases、observables、evidence targets、metrics、
  比較・計算方法、expected mechanism、protocol、resource、operational stop/impossibility/input/
  environment conditions を宣言する。evidence targets は後で読み返す observation / artifact の
  記録先を示すだけで、閾値や研究上の判定を含めない。計画時点の研究上の結論、案の採否、
  レビュー判断は実行開始条件にしない。
- metric、比較対象、observation、stopping rule、研究上の結果解釈は topic / research owner が
  必要な範囲で `README.md`、`provenance.toml`、`config.yaml` に定義する。
- `success`、`failed`、`blocked`、`incomplete` は実行の terminal / failure state であり、
  研究上の結論を表さない。
- exit status と artifact readback は実行・証跡の observation として記録し、それだけから
  研究上の成功を判定しない。
- 実行後の support / reject / inconclusive、threshold interpretation、review は topic / research
  owner の任意の結果解釈として report 等へ記録し、run の開始・完了をブロックしない。
- 共通 lifecycle は run identity、`result/<run-id>/raw/` / `summary/` の path、
  source/config/environment provenance、実在する artifact の role/checksum/readback、
  failure evidence を記録する。
- artifact は選択した producer / protocol が生成すると宣言したものだけを要求し、producer が
  宣言していない observation、metric、filename を全 topic に課さない。

## 可視化

可視化を必要とする topic は `visualization.py` の `render(run_dir, template_dir)` を実装し、
HTML または画像を `summary/` など契約された出力先へ書きます。`EXPERIMENT_RUN_VISUALIZATION=1`
で要求した renderer が利用できない場合、status は `blocked` となり、run の成功へ昇格しません。
既定 template は notebook、実行済み notebook、共通の `artifact_*` module を持ちません。

## 再現性と保持

実行 command、branch、commit、config、environment、seed、resource allocation、result identity、
cleanup policy は `provenance.toml` と summary snapshot の両方で読み戻せるようにします。raw は
要約から再計算できるよう保持し、summary は比較・レビューに必要な最小証跡として保持します。

`.gitignore` は未追跡 payload にだけ効きます。既に通常 Git で追跡された payload は、既存の
[`save_experiment_result_annex.py`](../../tools/experiments/artifacts/save_experiment_result_annex.py)
owner で圧縮 archive を作り、manifest の source digest、annex key、archive digest を読み戻してから
移行します。設定済みの special remote へ payload を保持する場合だけ、owner が指定した exact path に
対して `git annex copy --to <remote>`、取得側では `git annex get` を行い、content availability と
checksum を別に読み戻します。その readback が完了するまで `git rm --cached` を実行しません。
これは index entry だけを外す操作であり、作業 tree の入力やログを移動・削除する操作ではありません。

Git branch の通常の `push` は pointer/metadata の共有であって、annex payload の transfer ではありません。
special remote が無い場合は、archive を source checkout の外にある設定済みの local annex worktree / spool
へ保持し、local-only retention と明記します。source tree に payload を戻して remote durability を主張したり、
未指定 remote へ広く同期したりしません。source checkout の branch/index/既存 dirty paths を保全し、annex
worktree の clean 状態、archive key/content location、source/archive checksum をそれぞれ読み戻します。編集が必要な場合だけ owner の指示で
`git annex unlock` を使い、手動 symlink、`.git/annex` 内部 metadata、広い `git annex sync`、確認を迂回する
`git annex drop --force` は使いません。payload の分類は拡張子ではなく `data/`、canonical
`result/<run-id>/raw/` と compact summary/source/config/report の役割で行います。

稼働中 run は archive 対象の完成結果ではありません。process が利用している入力、ignored raw、log、
dirty working tree を保全し、terminal state と compact evidence が確定した後だけ retention 判断を
行います。topic branch には当該 topic の source と compact evidence だけを載せ、無関係な実験 payload
は集積せず、共通依存は registry / dependency reference で参照します。

保持期間と annex 移送は [documents/experiments/result-log-retention-and-visualization.md](../../documents/experiments/result-log-retention-and-visualization.md) の
契約に従います。
