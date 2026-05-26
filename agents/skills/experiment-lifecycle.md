# experiment-lifecycle
<!--
@dependency-start
responsibility Documents experiment-lifecycle for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
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
- main server host で formal run を回す場合は、`run_manifest.json` と `run.log` を残す wrapper を優先します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config.json` または YAML snapshot として保存します。
- smoke / formal の入口は project `Makefile` に置き、内側で `tools/experiments/run_managed_experiment.py` を呼びます。
- registered command は `{config_path}` を受け取ります。
- result / report 生成では `result-artifact-writeout` を使い、raw run output、summary report、manifest、unique run_name、overwrite policy を分けます。
- experiment plan、rerun plan、result report、HTML view の構造が非自明な場合は、run や report 生成の前に `structure-planning` を使い、first artifact、source-to-structure map、metric contract、invalid interpretation、validation gate を固定します。
