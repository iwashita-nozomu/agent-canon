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

experiment topic を review し、managed runner route と topic `run.py` inner entrypoint、
GPU/JAX 環境の所有境界、artifact / visualization.py renderer / README の契約が崩れていないかを確認します。

## Use When

- `experiments/<topic>/run.py`、`config.yaml`、`visualization.py`、README を review する
- managed runner route、topic `run.py` inner entrypoint、topic 構築 tooling の責務が混同されていないか確認する
- GPU preallocation、JAX platform、GPU visibility、worker 並列度の混入を確認する
- 実験結果 artifact、visualization.py renderer、registered command の整合を確認する

## Review Checklist

- `experiments/registry.toml` に topic があり、registered command は managed runner
  が呼ぶ topic `run.py` inner command になっている
- README の standard command は `python3 -m tools.experiments.execution.run_managed_experiment
  --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` と一致している
- managed run は既定 run directory を作り、topic `run.py` は必要に応じて
  `EXPERIMENT_RUN_DIR` を尊重して同じ artifact schema を書く
- topic code と checked-in config は GPU visibility、JAX platform、allocator、
  preallocation、`max_workers: 1`、単一 GPU 固定、serial throttle を持たない
- topic が renderer 実行や worker subprocess を起動する場合、その subprocess は
  `os.environ.copy()` または標準継承で caller environment を引き継ぐ
- run artifact は `summary/config_snapshot.json`、`summary/summary.json`、
  `summary/cases.jsonl`、raw case artifact を区別する
- `visualization.py` は artifact reader/renderer であり、formal run launcher や config 正本に
  なっていない

## Suggested Static Search

```bash
git grep -n -E "ExperimentRunner|EXPERIMENT_RUN_DIR|JAX_|XLA_|CUDA_VISIBLE|PREALLOC|prealloc|gpu_max_slots|max_workers|subprocess|ProcessPool|multiprocessing|env=" -- \
  experiments/<topic> experiments/registry.toml tools/experiments || true
```

## Findings Policy

- `fix now`: managed runner の inner command が topic `run.py` を呼ばない、
  topic-side environment hard-code、child subprocess environment reset、
  missing registry command、artifact path outside run dir.
- `follow-up`: README / visualization.py renderer explanation gap, optional artifact schema gap,
  weak visualization coverage.
- `no findings`: state the remaining unchecked surfaces, especially whether an
  actual formal run was intentionally skipped.
