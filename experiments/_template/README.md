# Experiment Topic Template

<!--
@dependency-start
contract reference
responsibility Documents the managed experiment topic scaffold.
upstream design ../../documents/experiment-registry.md defines managed experiment command protocol.
upstream implementation ../../tools/experiments/create_experiment_topic.py copies this template into project topics.
upstream implementation ../../tools/ci/check_experiment_registry.py validates project-owned registry entries that reference copied topics.
downstream implementation run.py provides the topic entrypoint.
downstream implementation cases.py defines the template case set.
downstream environment config.yaml stores template case and metric settings.
downstream implementation visualize.ipynb renders managed artifacts.
@dependency-end
-->

このディレクトリは、新しい managed experiment topic を始めるための正本雛形です。
テンプレートはファイルの役割だけをそろえ、実験固有の `main::main`、case、config、notebook 本文、出力 schema は topic 作成後に実装します。
正本 template path は `vendor/agent-canon/experiments/_template/` です。

## Files

- `run.py`: 実験の唯一の直接 entrypoint。run directory を決め、artifact を生成し、`visualize.ipynb` をその run の文脈で実行する。
- `visualize.ipynb`: run artifact を読む notebook。本文は実験ごとに置き換える。
- `config.yaml`: topic 固有設定の置き場。
- `cases.py`: case 定義の置き場。
- `result/`: run artifact の置き場。

## Create Topic

最初に実験名 `<topic>` を固定し、AgentCanon template path
`vendor/agent-canon/experiments/_template/` を `experiments/<topic>/` へコピーする。

```bash
cp -r vendor/agent-canon/experiments/_template experiments/<topic>
```

topic 作成後は次の順に編集する。

1. `run.py` の `main::main`
1. `cases.py`
1. `config.yaml`
1. `visualize.ipynb`
1. `README.md`

## Run Contract

- formal run は `tools/experiments/run_managed_experiment.py --topic <topic> --use-registered-command formal` で起動します。
- registered command は topic-local `run.py` に `{run_dir}` と `{config_path}` を渡します。
- managed runner は `run_manifest.json`、`eval_manifest.json`、`artifact_manifest.json`、`command.json`、`environment.json`、`source_snapshot.json`、`config.json`、`config_source.yaml`、`run.log`、`logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log` を作ります。
- `config.yaml` は managed runner の起動前提です。`source_snapshot.json` は topic source、registry、command source、runner source、dirty source file の digest と git status を持ちます。
- `run.py` を直接実行する経路は topic 実装中の局所確認用です。正式結果に使う run は managed runner を通し、`EXPERIMENT_RUN_DIR` が指す run directory へ artifact を書きます。
- `run.py` は `visualize.ipynb` を実行し、notebook 実行時は `EXPERIMENT_RUN_DIR` が run directory を指します。
- template の topic 実装が最初に追加する domain artifact は `summary.json`、`cases.jsonl`、必要な `logs/` artifact、`visualize_executed.ipynb` です。
