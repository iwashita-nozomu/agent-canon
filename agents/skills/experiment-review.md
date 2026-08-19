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
GPU/JAX 環境の所有境界、同一 identity から導出される compact `result/` と ignored `raw/`、
artifact / notebook / README の契約が崩れていないかを確認します。

## Use When

- `experiments/<topic>/run.py`、`config.yaml`、`visualize.ipynb`、README を review する
- managed runner route、topic `run.py` inner entrypoint、topic 構築 tooling の責務が混同されていないか確認する
- GPU preallocation、JAX platform、GPU visibility、worker 並列度の混入を確認する
- 実験結果 artifact、raw retention、notebook、registered command の整合を確認する

## Review Checklist

- `experiments/registry.toml` に topic があり、registered command は managed runner
  が呼ぶ topic `run.py` inner command になっている
- README の standard command は `python3 -m tools.experiments.run_managed_experiment
  --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` と一致している
- managed run は一つの `ExperimentIdentity` から canonical result/raw directory を作り、topic `run.py` は
  `EXPERIMENT_RUN_DIR` と `EXPERIMENT_RAW_DIR` を尊重する。topic 側で variant/run name を再解析しない
- topic code と checked-in config は GPU visibility、JAX platform、allocator、
  preallocation、`max_workers: 1`、単一 GPU 固定、serial throttle を持たない
- topic が notebook 実行や worker subprocess を起動する場合、その subprocess は
  `os.environ.copy()` または標準継承で caller environment を引き継ぐ
- `result/<variant>/<run_name>/` は config/source/environment snapshot、`summary.json`、`cases.jsonl`、manifest、failure evidence など compact review evidence に限定する
- `raw/<variant>/<run_name>/` は原データ、長大ログ、dump、再生成可能な中間生成物の唯一の source-side home であり、`raw/.gitignore` 自身を除いて通常 Git で追跡しない
- raw annex archive は `save_experiment_result_annex.py --raw-dir ...` の一つの owner だけが作り、Summary、result manifest、Markdown report を archive に複製しない
- `visualize.ipynb` は artifact reader であり、formal run launcher や config 正本に
  なっていない
- notebook の各可視化項目は、直前の Markdown cell に日本語で入力 artifact、
  描く量、読み方を説明している

## Suggested Static Search

```bash
git grep -n -E "ExperimentRunner|EXPERIMENT_RUN_DIR|EXPERIMENT_RAW_DIR|JAX_|XLA_|CUDA_VISIBLE|PREALLOC|prealloc|gpu_max_slots|max_workers|subprocess|ProcessPool|multiprocessing|env=" -- \
  experiments/<topic> experiments/registry.toml tools/experiments || true
```

## Findings Policy

- `fix now`: managed runner の inner command が topic `run.py` を呼ばない、
  topic-side environment hard-code、child subprocess environment reset、
  missing registry command、identity と一致しない result/raw path、bulky raw artifact の result 混入、Summary/report の raw archive 重複収録。
- `follow-up`: README / notebook explanation gap, optional artifact schema gap,
  weak visualization coverage.
- `no findings`: state the remaining unchecked surfaces, especially whether an
  actual formal run was intentionally skipped.
