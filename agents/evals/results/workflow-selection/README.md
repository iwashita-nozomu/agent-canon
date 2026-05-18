# Workflow Selection Eval Results

<!--
@dependency-start
responsibility Documents accumulated workflow selection eval result naming.
upstream design ../../README.md eval result accumulation contract
upstream design ../../workflow_selection_eval.toml workflow selection eval manifest
downstream implementation ../../../../tools/agent_tools/evaluate_workflow_selection.py writes reports
downstream implementation ../../../../tools/agent_tools/eval_accumulation_check.py validates reports
downstream implementation ../../../../tools/agent_tools/generate_agent_runtime_dashboard.py summarizes reports
@dependency-end
-->

This directory stores append-only workflow selection eval reports.

The eval checks the hook-owned prompt routing classifier against frozen prompt
cases in `agents/evals/workflow_selection_eval.toml`. It exists to catch cases
where a user request should select a known workflow but the prompt-intake logger
does not emit the expected candidate workflow.

File names use:

```text
workflow-selection-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-hash>-<status>.md
```

Each report contains `WORKFLOW_SELECTION_EVAL_RUN_ID=...` and
`WORKFLOW_SELECTION_EVAL_STATUS=<pass|fail>`. Reports do not copy raw prompt
text; they list case IDs and observed routing labels only.

Run the eval without accumulating for CI-style checks:

```bash
python3 tools/agent_tools/evaluate_workflow_selection.py --root .
```

Use `--accumulate` when the run itself should become durable AgentCanon evidence:

```bash
python3 tools/agent_tools/evaluate_workflow_selection.py --root . --accumulate
```
