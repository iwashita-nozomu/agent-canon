# Experiment Topic Template

このディレクトリは、新しい experiment topic を始めるための最小雛形です。
server 上でそのまま回せるように、`cases.py`、`experimentcode.py`、`result/` の入口をそろえています。

## Question

<!-- この topic が何を確かめる実験なのかを書く -->

## Comparison Target

<!-- main、baseline、reference method などを書く -->

## Standard Commands

smoke:

```bash
python3 scripts/experiments/run_managed_experiment.py \
  --topic <topic> \
  --use-registered-command smoke
```

formal run:

```bash
python3 scripts/experiments/run_managed_experiment.py \
  --topic <topic> \
  --use-registered-command formal
```

## Expected Outputs

- `result/<run_name>/run_manifest.json`
- `result/<run_name>/run.log`
- `result/<run_name>/summary.json`
- `result/<run_name>/cases.jsonl`
- `experiments/report/<run_name>.md`

## Notes

- `cases.py` は case 列の定義に集中させます。
- `experimentcode.py` は CLI、orchestration、summary 出力に集中させます。
- `experiments/registry.toml` に topic entry を追加し、`smoke_inner_command` と `formal_inner_command` を正本にします。
- formal run では `run_name` と protocol を固定した fresh 実行にします。
