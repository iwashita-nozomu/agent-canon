# experiment-lifecycle
<!--
@dependency-start
responsibility Documents experiment-lifecycle for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
@dependency-end
-->


## Purpose

実験の準備、初期化、実行、結果整理、review、再実行判断を一続きの運用として扱います。

## Use When

- experiment directory の初期化
- case 群の実行
- result / report 生成
- critical review と report review を挟んだ実験反復
- rerun、追加検証、report 書き直しの分岐

## Core References

- `agents/workflows/experiment-workflow.md`
- `documents/experiment-registry.md`
- `agents/workflows/research-workflow.md`
- `tools/experiments/run_managed_experiment.py`

## Role In Research-Driven Change

- この skill は `Research-Driven Change` の inner loop です。
- 外側の仮説更新や次の change 決定は `research-workflow` が扱います。
- この skill は 1 つの protocol と 1 回の run、またはその直後の rewrite / extra validation / rerun 分岐を扱います。

## Boundary

- この repo の実験運用正本は `agents/workflows/experiment-workflow.md` です。
- 実験結果を見ながら code change、調査、チューニングまで含めた loop を回す場合は `adaptive-improvement-loop` を追加します。
- topic の entrypoint と formal command は `experiments/registry.toml` を正本にします。
- 新規 topic は最初に実験名を固定し、AgentCanon template path `vendor/agent-canon/experiments/_template/` を `experiments/<topic>/` へコピーして始めます。
- コピー後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualize.ipynb`、`README.md` の順で編集します。
- main server host で formal run を回す場合は、`run_manifest.json` と `run.log` を残す wrapper を優先します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config.json` または YAML snapshot として保存します。
- topic README は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、出力 schema、run_name 規則を固定する入口です。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook に置き、formal run の起動や設定正本にはしません。
- 各 run は `result/<run_name>/logs/` を持ちます。top-level `run.log` は managed runner の互換ログとして残し、追加ログは `logs/` に分けます。
- smoke / formal の入口は project `Makefile` に置き、内側で `tools/experiments/run_managed_experiment.py` を呼びます。
- registered command は `{config_path}` を受け取ります。
- result / report 生成では `result-artifact-writeout` を使い、raw run output、summary report、manifest、unique run_name、overwrite policy を分けます。
- experiment plan、rerun plan、result report、HTML view の構造が非自明な場合は、run や report 生成の前に `structure-planning` を使い、first artifact、source-to-structure map、metric contract、invalid interpretation、validation gate を固定します。
- experiment plan / report の paragraph order、causal transition、evidence-to-claim transition が非自明な場合は、`structure-planning` 側で `agent-canon semantic-index discourse-relations --profile experiment-report` または `--profile methods-protocol` を使い、discourse edge を構造 evidence として保存します。
- prose graph handoff がある場合は、hypothesis / metric / baseline / expected-result diagnostics を experiment plan または rerun plan の入力にします。
