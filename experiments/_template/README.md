# Experiment Topic Template

<!--
@dependency-start
contract reference
responsibility Documents the experiment topic scaffold.
upstream design ../../documents/experiment-registry.md defines experiment command protocol.
upstream implementation ../../tools/experiments/create_experiment_topic.py copies this template into project topics.
upstream implementation ../../tools/ci/check_experiment_registry.py validates project-owned registry entries that reference copied topics.
downstream implementation run.py provides the topic entrypoint.
downstream implementation cases.py defines the template case set.
downstream environment config.yaml stores template case and metric settings.
downstream implementation visualize.ipynb renders topic run artifacts.
@dependency-end
-->

このディレクトリは、新しい experiment topic を構築するための正本雛形です。
テンプレートはファイルの役割だけをそろえ、実験固有の
`run_experiment()`、`run_case_worker()`、case、config、notebook 本文、出力
schema は topic 作成後に実装します。
正本 template path は `vendor/agent-canon/experiments/_template/` です。

## Files

- `run.py`: 実験の正本 entrypoint。オプションなしで run directory を作り、artifact を生成し、`visualize.ipynb` をその run の文脈で実行する。
- `visualize.ipynb`: run artifact を読む notebook。本文は実験ごとに置き換える。
- `config.yaml`: topic 固有設定の置き場。
- `cases.py`: case 定義の置き場。
- `result/`: run artifact の置き場。

## Create Topic

最初に実験名 `<topic>` を固定し、topic 作成 tool で AgentCanon template path
`vendor/agent-canon/experiments/_template/` を project-root
`experiments/<topic>/` へコピーし、project registry に topic entry を追加する。

```bash
python3 tools/experiments/create_experiment_topic.py <topic>
```

topic 作成後は次の順に編集する。

1. `run.py` の `run_experiment()` と `run_case_worker()`
1. `cases.py`
1. `config.yaml`
1. `visualize.ipynb`
1. `README.md`

## Run Contract

- 標準実行 command は topic `run.py` のオプションなし直実行です。

```bash
/usr/bin/python /workspace/experiments/<topic>/run.py
```

- `run.py` は `experiments/<topic>/result/<topic>_<timestamp>/` に run artifact を作ります。
- `config.yaml` は checked-in 設定正本です。topic 実装は run directory に `config_snapshot.json` などの設定 snapshot を保存します。
- `run.py` は `visualize.ipynb` を実行し、notebook 実行時は `EXPERIMENT_RUN_DIR` が run directory を指します。
- template の topic 実装が最初に追加する domain artifact は `summary.json`、`cases.jsonl`、必要な `logs/` artifact、`visualize_executed.ipynb` です。
- project registry を使う場合も、registered command は topic-local `run.py` を直接呼び、topic 作成 tool や別の実行補助 command を再帰呼びしません。

## Implementation Markers

- `run.py` の top-level import は `from __future__ import annotations` と定数だけにします。
- `run.py` の `main()` は引数なしで固定し、CLI 引数や `argparse` を追加しません。
- JAX、CUDA、NumPy、EQX、Optax、project module などの実験依存 import は、`run_experiment()` または `run_case_worker()` 内に書きます。
- GPU visibility、JAX platform、allocator、preallocation などの実行環境割当は caller environment または scheduler に任せ、topic code / checked-in config には埋め込みません。
- 実験を書く場所は、`run.py`、`cases.py`、`config.yaml`、`visualize.ipynb` 内の `IMPLEMENT HERE` コメントです。
