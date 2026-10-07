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

## Review Procedure

1. `experiments/registry.toml` の registered command が managed runner から topic の
   `run.py` を呼ぶことを確認する。README の標準入口は次の形です。
   `python3 -m tools.experiments.execution.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py`
2. runner が作る run directory と `EXPERIMENT_RUN_DIR`、topic config、raw/summary artifact の
   境界を確認する。`visualization.py` は reader/renderer であり、launcher や config 正本ではない。
3. topic code/config に GPU visibility、JAX platform、allocator、preallocation、単一 GPU 固定、
   serial throttle がないことを確認する。child process があれば caller environment を継承することも見る。
4. 比較対象・case set・denominator・failure pattern・baseline を揃え、correctness、stability、
   performance、解釈、limitation を分けて結果を読む。

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
[documents/experiments/experiment-report-style.md](../../documents/experiments/experiment-report-style.md) を参照します。ここでは reader-facing
文章を再作成せず、結果と claim の対応だけを判定します。

## Static Search

```bash
git grep -n -E "ExperimentRunner|EXPERIMENT_RUN_DIR|JAX_|XLA_|CUDA_VISIBLE|PREALLOC|prealloc|gpu_max_slots|max_workers|subprocess|ProcessPool|multiprocessing|env=" -- \
  experiments/<topic> experiments/registry.toml tools/experiments || true
```

## Findings

- `fix now`: managed runner の inner command が topic `run.py` を呼ばない、
  topic-side environment hard-code、child subprocess environment reset、
  missing registry command、artifact path outside run dir.
- `follow-up`: README / visualization.py renderer explanation gap, optional artifact schema gap,
  weak visualization coverage.
- `no findings`: 残る未確認 surface と formal run を意図的に省略したか、claim が観測範囲に
  限定されているかを記録する。
