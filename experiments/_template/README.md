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
テンプレートは `main()`、`run_experiment()`、`run_case_worker()`、case、config、
notebook 本文、出力 schema の役割だけをそろえます。正式な実行は
`tools/experiments/run_managed_experiment.py` が選択済み command を一つの
ExperimentRunner task へ適合し、managed child から `main()` を呼び出します。
正本 template path は `vendor/agent-canon/experiments/_template/` です。

## Files

- `run.py`: 実験の正本 entrypoint。`main()` は managed runner の child からのみ呼び出し、run artifact を生成する。
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

- topic `run.py` の直接実行は typed prohibition です。正式な command は managed CLI です。

```bash
/usr/bin/python tools/experiments/run_managed_experiment.py --topic <topic> -- /usr/bin/python /workspace/experiments/<topic>/run.py
```

- `run.py` は `experiments/<topic>/result/<topic>_<timestamp>/` に run artifact を作ります。
- `config.yaml` は checked-in 設定正本です。topic 実装は run directory に `config_snapshot.json` などの設定 snapshot を保存します。
- notebook は reader artifact であり、topic `main()` から subprocess 実行しません。必要な notebook 処理は managed runner の別の選択済み task として設計します。
- template の topic 実装が最初に追加する domain artifact は `summary.json`、`cases.jsonl`、必要な `logs/` artifact です。
- project registry を使う場合も、registered command は topic-local `run.py` の `main()` へ canonical adapter で到達し、topic 作成 tool や別の実行補助 command を再帰呼びしません。

## Implementation Markers

- `run.py` の top-level import は `from __future__ import annotations` と定数だけにします。
- `run.py` の `main()` は引数なしで固定し、CLI 引数や `argparse` を追加しません。
- JAX、CUDA、NumPy、EQX、Optax、project module などの実験依存 import は、`run_experiment()` または `run_case_worker()` 内に書きます。
- GPU visibility、JAX platform、allocator、preallocation などの実行環境割当は caller environment または scheduler に任せ、topic code / checked-in config には埋め込みません。
- 実験を書く場所は、`run.py`、`cases.py`、`config.yaml`、`visualize.ipynb` 内の `IMPLEMENT HERE` コメントです。
