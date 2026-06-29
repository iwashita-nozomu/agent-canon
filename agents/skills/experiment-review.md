# experiment-review
<!--
@dependency-start
contract skill
responsibility Documents experiment-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design experiment-lifecycle.md experiment lifecycle workflow
@dependency-end
-->

## Purpose

experiment topic を review し、`run.py` 直実行、GPU/JAX 環境の所有境界、
artifact / notebook / README の契約が崩れていないかを確認します。

## Use When

- `experiments/<topic>/run.py`、`config.yaml`、`visualize.ipynb`、README を review する
- `run.py` オプションなし直実行 entrypoint と topic 構築 tooling の責務が混同されていないか確認する
- GPU preallocation、JAX platform、GPU visibility、worker 並列度の混入を確認する
- 実験結果 artifact、notebook、registered command の整合を確認する

## Review Checklist

- `experiments/registry.toml` に topic があり、registered command は topic
  `run.py` entrypoint を直接呼んでいる
- README の standard command は `/usr/bin/python experiments/<topic>/run.py`
  のオプションなし直実行を明示している
- direct `run.py` は既定 run directory を作り、必要に応じて
  `EXPERIMENT_RUN_DIR` を尊重して同じ artifact schema を書く
- topic code と checked-in config は GPU visibility、JAX platform、allocator、
  preallocation、`max_workers: 1`、単一 GPU 固定、serial throttle を持たない
- topic が notebook 実行や worker subprocess を起動する場合、その subprocess は
  `os.environ.copy()` または標準継承で caller environment を引き継ぐ
- run artifact は config snapshot、`summary.json`、`cases.jsonl`、case artifact、
  `visualize_executed.ipynb` を区別する
- `visualize.ipynb` は artifact reader であり、formal run launcher や config 正本に
  なっていない
- notebook の各可視化項目は、直前の Markdown cell に日本語で入力 artifact、
  描く量、読み方を説明している

## Suggested Static Search

```bash
rg -n "ExperimentRunner|EXPERIMENT_RUN_DIR|JAX_|XLA_|CUDA_VISIBLE|PREALLOC|prealloc|gpu_max_slots|max_workers|subprocess|ProcessPool|multiprocessing|env=" \
  experiments/<topic> experiments/registry.toml tools/experiments -S
```

## Findings Policy

- `fix now`: registered command が topic `run.py` を直接呼ばない、
  topic-side environment hard-code、child subprocess environment reset、
  missing registry command、artifact path outside run dir.
- `follow-up`: README / notebook explanation gap, optional artifact schema gap,
  weak visualization coverage.
- `no findings`: state the remaining unchecked surfaces, especially whether an
  actual formal run was intentionally skipped.
