# experiment-review
<!--
@dependency-start
contract skill
responsibility Documents experiment-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design experiment-lifecycle.md experiment lifecycle workflow
upstream design research-workflow.md research claim and comparison boundary
upstream design ../../documents/experiments/experiment-critical-review.md critical evidence review
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

## Evidence Review

数値が改善していても、次の境界が崩れていれば claim を受理しません。

- 比較対象と case set が一致し、failure を都合よく除外していない
- 平均だけでなく、case 数、success rate、failure kind、代表値、ばらつき、baseline 差分が
  claim の強さに見合っている
- 実験 code が equation、assumptions、parameter、method contract と一致している
- correctness、numerical stability、performance、failure pattern を別々に解釈している
- 改善指標の裏で悪化した指標、case mix、failure-onset、environment noise を見落としていない
- figure / table の軸、単位、scale、denominator、missingness、baseline が読み取れ、計算式と
  source artifact に辿れる
- 観測事実、支持された解釈、推測、missing evidence、overclaim risk、limitation を分けている
- toy-only、単一 difficulty 帯、baseline 未比較から scalability、superiority、広い theorem
  を主張していない

正式な report をレビューする場合は、`report-writing` が選んだ本文構成と
`documents/experiments/experiment-report-style.md` を参照します。ここでは reader-facing
文章を再作成せず、結果と claim の対応だけを判定します。

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
  actual formal run was intentionally skipped, and whether the claim was limited
  to the observed population.
