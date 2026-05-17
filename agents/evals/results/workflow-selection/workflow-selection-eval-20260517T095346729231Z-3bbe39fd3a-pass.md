# Workflow Selection Eval

<!--
@dependency-start
responsibility Records one workflow selection eval run.
upstream implementation ../../../../tools/agent_tools/evaluate_workflow_selection.py generates this report
@dependency-end
-->

WORKFLOW_SELECTION_EVAL_RUN_ID=workflow-selection-eval-20260517T095346729231Z-3bbe39fd3a
WORKFLOW_SELECTION_EVAL_STATUS=pass
WORKFLOW_SELECTION_EVAL_CASES=4
WORKFLOW_SELECTION_EVAL_FAILED=0
manifest: `agents/evals/workflow_selection_eval.toml`

| case | status | expected workflows | observed workflows | missing | forbidden seen |
| --- | --- | --- | --- | --- | --- |
| `environment-maintenance-container-ci` | `pass` | `environment-maintenance`, `codex-task-workflow` | `codex-task-workflow`, `environment-maintenance` | `none` | `none` |
| `adaptive-loop-next-action` | `pass` | `adaptive-improvement-loop` | `adaptive-improvement-loop` | `none` | `none` |
| `agent-canon-pr-merge` | `pass` | `agent-canon-pr-workflow` | `agent-canon-pr-workflow` | `none` | `none` |
| `repo-changing-implementation` | `pass` | `codex-task-workflow` | `codex-task-workflow` | `none` | `none` |
