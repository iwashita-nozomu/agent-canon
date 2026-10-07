# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Owns experiment run identity, lifecycle state, reproducibility core, and explicit rerun/publication decisions without owning artifact files or report prose.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
downstream implementation ../../tools/validation/semantic/tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
@dependency-end
-->

## Purpose

実験の準備、実行、終端状態、結果整理、rerun 判断を一続きで扱います。run identity、source/config/command/environment の
provenance、failed/partial を含む terminal status をこの skill が記録し、実在 artifact は
`result-artifact-writeout`、reader-facing claim は `report-writing`、annex retention は明示的な archive writer に委譲します。

## Use When

- experiment topic の初期化、case 実行、result/report 生成、review、rerun を行う
- 一つの protocol と run の終端状態を再現可能に記録する

## Topic Preparation

topic 名と registry identity を決め、唯一の creator route を実行します。

```bash
python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>
```

作成後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualization.py`、`README.md` の順に確認します。
template の直接コピーや別 scaffold fallback は使いません。

## Run procedure

1. 必要な範囲で `Question`、`Comparison Target`、`Stop Condition`、`Fairness Notes`、`Artifact Plan`、
   `Registry Plan`、`Config Snapshot Plan`、`Execution Plan` を固定する。準備、実装、static check、run、report は独立した段階とする。
2. `debug`/`smoke`（局所確認）、`verified`（bounded run）、`formal`（case set、timeout、dtype、backend、worker、output を固定した比較 run）から選ぶ。
3. formal/verified の入口は次を使う。
   `python3 -m tools.experiments.execution.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py`
4. source、effective config、command、environment、run identity、terminal status を記録し、producer が選んだものだけを
   `result/<run-id>/raw/` と `result/<run-id>/summary/` に渡す。`visualization.py` は artifact reader/renderer で、launcher や config 正本ではない。
5. spot、都合のよい subset、途中停止や partial run は formal evidence にしない。停止は `Stop Reason:` と `Restart Decision:` を残し、rerun は新しい run identity で最初から行う。

## Failed experiment cleanup

実行中、未実施、終端未確認だけでは失敗と断定しません。失敗が確定したら、その run 専用の code/config と raw、summary、log、checkpoint、図表、report を削除します。
共有実装・入力、成功 run、独立した有効 case は残します。保持できる唯一の例外は、支配式・仕様・既存観測で物理的限界が原因だと説明できる場合です。NaN/Inf、未収束、OOM、timeout、crash だけではその根拠になりません。
削除不能な対象は具体的な owner/action とともに記録し、削除済みとは報告しません。

## Long GPU or crash branch

長時間 GPU run の開始/延長や crash 後の rerun では、高負荷設定を即時再投入せず、既存ログ・最後の進捗・run identity を確認します。
compile と run を分け、有限の resource、期限、停止条件、永続保存先を実際に read back できる場合だけ開始します。
診断は許可された static check、bounded CPU test、上限を確認した小さな GPU check の順に進め、前段成功から長時間 rerun を自動起動しません。
topic に mini-runner、scheduler、独自 signal 回収、partial-resume protocol を追加せず、managed runner/scheduler owner に handoff します。

## Topic boundary

- `run.py` は orchestration、`cases.py` は case/difficulty/resource estimate、`task(case, context)` は一 case の研究 logic を持つ。
- process lifecycle、timeout、child cleanup、worker completion、GPU/CPU slot、child environment propagation は managed runner が持つ。
- checked-in config は `experiments/<topic>/config.yaml`、topic README は問い・比較対象・標準 command・config source・renderer・output schema・run name を説明する。
- project registry がある場合は `python3 -m tools.validation.ci.checks.check_experiment_registry` を実行し、execution surface の変更は owner-selected test を使う。
- result artifact の role/checksum/readback は `result-artifact-writeout`、reader-facing report は要求時だけ `report-writing`、HTML は要求時だけ `html-output` に委譲する。
- annex retention は必要時だけ次を明示実行する。
  `python3 -m tools.experiments.artifacts.save_experiment_result_annex --result-dir experiments/<topic>/result/<run_name> --annex-repo "$EXPERIMENT_RESULT_ANNEX_REPO"`

`research-workflow` は複数 iteration の仮説と claim、`adaptive-improvement-loop` は backlog-driven sequence、
`experiment-review` は topic contract の review を所有します。構造が本当に未決定な plan/report だけ `structure-planning` を追加します。
