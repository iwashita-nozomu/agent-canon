# research-perspective-review

## Purpose

研究系の変更や実験証拠を、複数の独立視点で並列レビューします。

## Use When

- benchmark protocol、artifact policy、reporting policy の大きな変更
- `experiments/`、`experiments/report/`、`notes/experiments/` を含む repo-wide review
- 研究 workflow、研究文書、比較設計の大きな整理
- method 採否や報告方針を `main` に持ち帰る前の独立レビュー

## Must Read Before Reviewing

- `documents/research-workflow.md`
- `documents/experiment-workflow.md`
- `documents/experiment-critical-review.md`
- `documents/REVIEW_PROCESS.md`

## Default Perspective Pack

repo-wide な research cleanup や methodology / artifact / reporting policy の変更では、まず 6 視点すべてを使います。
scope が狭い場合だけ、使わない視点を明示して subset に落とします。

1. `reproducibility`
  - provenance、seed、command、environment、rerunability
1. `scientific-computing`
   - incremental change、testing、automation、prototype discipline
1. `benchmark`
   - fairness、confounders、case mix、anti-pattern
1. `artifact`
   - code、script、raw result、environment、rerun package の十分性
1. `fair-data`
   - metadata、命名、再利用性、result path と note path の可搬性
1. `ml-science-reporting`
   - assumptions、limitations、uncertainty、reader-facing reporting

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
- runtime smoke test が必要なときは `python3 scripts/agent_tools/smoke_test_research_perspective_pack.py`
