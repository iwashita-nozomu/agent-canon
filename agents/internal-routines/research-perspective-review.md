# research-perspective-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents research-perspective-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

研究系の変更や実験証拠を、複数の独立視点で並列レビューします。

## Use When

- benchmark protocol、artifact policy、reporting policy の大きな変更
- `experiments/`、`experiments/report/`、`documents/notes/experiments/` を含む repo-wide review
- 研究 workflow、研究文書、比較設計の大きな整理
- method 採否や報告方針を `main` に持ち帰る前の独立レビュー

## Review perspectives

依頼と観測結果から、独立に確認する価値がある観点を選びます。対象の研究・実験・報告の
正本を参照します。同じ根拠を確認する観点はまとめて扱います。

## Perspective To Subagent Mapping

- `reproducibility` -> `reproducibility_reviewer`
- `scientific-computing` -> `scientific_computing_reviewer`
- `benchmark` -> `benchmark_reviewer`
- `artifact` -> `artifact_reviewer`
- `fair-data` -> `fair_data_reviewer`
- `ml-science-reporting` -> `ml_science_reviewer`

## Outputs

- findings-first の perspective review
- perspective ごとの findings と follow-up
- `fix now`、`follow-up`、`delete-ok` の切り分け
