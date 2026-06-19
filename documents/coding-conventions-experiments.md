# 実験運用規約
<!--
@dependency-start
responsibility Documents 実験運用規約 for this repository.
upstream design README.md durable document index
@dependency-end
-->


この文書は、`experiments/` 配下の実験コード、benchmark、実験結果、実行環境の運用を扱います。
研究の問い、数式、比較対象、逐次改造の記録方法は `agents/workflows/research-workflow.md` を正本とします。
準備、実装、静的チェック、実行、結果レポートの標準手順は `agents/workflows/experiment-workflow.md` を参照してください。

## 1. 対象

- 実験コード
- benchmark コード
- 実行ごとの生成物
- 実験 report

## 2. ディレクトリ構成

- 実験は `experiments/<topic>/` に置きます。
- topic ごとに `README.md`、`run.py`、`cases.py`、`config.yaml`、`visualize.ipynb`、`result/` を基準にします。
- `experiments/<topic>/README.md` は、その topic の実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、出力 schema、run_name 規則を持つ正本 entrypoint です。
- 新規 topic は、実験名を固定してから AgentCanon template path `vendor/agent-canon/experiments/_template/` を `experiments/<topic>/` へコピーし、`run.py` の `main::main`、`cases.py`、`config.yaml`、`visualize.ipynb`、`README.md` の順で編集します。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook に置きます。notebook は結果確認と図表化の入口であり、正式 run の起動、細かな test、設定正本の置き場にしません。
- topic の正本 entrypoint と smoke / formal command は `experiments/registry.toml` に集約します。
- 1 回の run の report は `experiments/report/<run_name>.md` に置きます。
- 複数 run をまたぐ要約や知見は `notes/experiments/` や `notes/themes/` に置きます。
- server 上の formal run では `result/<run_name>/run_manifest.json`、`eval_manifest.json`、`run.log`、`logs/` を残します。追加 stdout / stderr、tool log、diagnostic log は `result/<run_name>/logs/` に置きます。

## 3. 実行原則

- 1 回の run は 1 つの `run_name` と 1 つの出力先に閉じた fresh 実行として扱います。
- partial run を正式結果として継ぎ足しません。
- 比較条件は run 開始前に固定します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置きます。
- 実験設定は Python object の暗黙状態ではなく、YAML で管理し、run 開始時に再現可能な artifact として snapshot します。
- formal run では `result/<run_name>/config.json` を必須 artifact とし、seed、case 範囲、timeout、dtype、backend、worker 数、allocator、feature flag、比較対象を run 開始前に書き出します。
- 各 run は `result/<run_name>/logs/` を持ちます。top-level `run.log` は managed runner の互換ログとして残し、topic 固有の追加ログは `logs/` 配下へ分けます。
- 巨大な生成物や raw ログを `main` の入口文書へ混ぜません。
- main server host で実行する run は、topic README に exact command と wrapper の使い方を明記します。
- 実験実行コマンドは project `Makefile` に用意します。長い `python3 ...` command を README や chat だけに残して正式手順にしません。
- formal / server-side run は必ず `tools/experiments/run_managed_experiment.py`、または同等に `run_manifest.json`、`config` snapshot、`run.log`、exit status を保存する wrapper から起動します。
- 可視化 notebook は run 後に `summary.json`、`cases.jsonl`、必要な `logs/` artifact を読むだけにし、notebook の hidden state を正式 evidence にしません。
- `experiment_runner` を使う実験で、process 管理、GPU 割当、timeout、signal cleanup を実験本体に実装しません。

## 3.1 設定 snapshot

- 実験 script は `--config <path>` または同等の引数で、topic の YAML config を読めるようにします。
- `experiments/<topic>/config.yaml` は human-authored な設定正本です。default 値を Python module global や notebook cell state だけに閉じ込めることを禁止します。
- `tools/experiments/run_managed_experiment.py` を使う run では、wrapper が `result/<run_name>/config.json` を生成し、`EXPERIMENT_CONFIG_PATH` と `{config_path}` placeholder で inner command に渡します。
- YAML を正本にする topic では、Make target が `config.yaml` を run 用 snapshot へ変換するか、inner command が `config.yaml` を読み、`result/<run_name>/config.yaml` と digest を保存します。いずれの場合も `run_manifest.json` から設定正本を辿れるようにします。
- `experiments/registry.toml` の `smoke_inner_command` と `formal_inner_command` は `{config_path}` を含めます。
- `summary.json` には、少なくとも `config_path` または config digest / config key list を残します。
- 実験中に Python closure、module global、notebook cell state、環境変数だけで条件を変えた場合、その run は正式 evidence にしません。

## 3.2 Make target と実行入口

各 project は、実験 topic ごと、または registry topic 共通で、次の入口を `Makefile` に置きます。

```makefile
.PHONY: experiment-check experiment-smoke experiment-formal

experiment-check:
  python3 tools/ci/check_experiment_registry.py

experiment-smoke:
  python3 tools/experiments/run_managed_experiment.py \
    --topic $(TOPIC) \
    --variant smoke \
    --config-json experiments/$(TOPIC)/config.json \
    --use-registered-command smoke

experiment-formal:
  python3 tools/experiments/run_managed_experiment.py \
    --topic $(TOPIC) \
    --variant formal \
    --config-json experiments/$(TOPIC)/config.json \
    --use-registered-command formal
```

YAML を checked-in 正本にする repo では、上の `--config-json` は
project-local helper で `experiments/$(TOPIC)/config.yaml` から生成した
snapshot JSON に置き換えます。重要なのは、手元だけの ad hoc command ではなく、
`make experiment-smoke TOPIC=<topic>` と `make experiment-formal TOPIC=<topic>`
で同じ runner 経路を再実行できることです。

topic 固有の target 名を置く場合も、内側では同じ managed runner を呼びます。

```makefile
.PHONY: demand-site-battery-smoke demand-site-battery-formal

demand-site-battery-smoke:
  $(MAKE) experiment-smoke TOPIC=demand_site_battery_control

demand-site-battery-formal:
  $(MAKE) experiment-formal TOPIC=demand_site_battery_control
```

直接許可するのは、開発中の `--help`、import check、単一 case の debugger 起動だけです。
正式な smoke / formal / server-side run は Make target から managed runner を通します。

## 3.3 禁止事項

- formal / server-side run を notebook、chat、または未登録の ad hoc command だけから起動して正式 evidence にすることを禁止します。
- 実験設定を Python closure、module global、notebook cell state、または環境変数だけに閉じ込めることを禁止します。
- `experiment_runner` を使う実験で、process 管理、GPU 割当、timeout、signal cleanup を実験本体に重複実装することを禁止します。

## 4. report と notes

- 1 回の run の一次 report は `experiments/report/` に置きます。
- 複数 run の比較や再利用知識は `notes/` に残します。
- `Results` と `Discussion` を混ぜません。
- 解釈と limitation を同じ文書内で確認できるようにします。

## 5. branch 方針

- 実験も既定では `main` 基準で進めます。
- branch や worktree は隔離が必要な場合だけ使います。
- branch 固有の台帳を長期保存先にしません。
