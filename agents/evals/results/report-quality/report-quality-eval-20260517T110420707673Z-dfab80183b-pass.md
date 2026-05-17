# Report Quality Eval

<!--
@dependency-start
responsibility Records one report quality eval run.
upstream implementation ../../../../tools/agent_tools/evaluate_report_quality.py generates this report
@dependency-end
-->

REPORT_QUALITY_EVAL_RUN_ID=report-quality-eval-20260517T110420707673Z-dfab80183b
REPORT_QUALITY_EVAL_STATUS=pass
REPORT_QUALITY_EVAL_TARGETS=3
REPORT_QUALITY_EVAL_CHECKS=9
REPORT_QUALITY_EVAL_FAILED=0
REPORT_QUALITY_EVAL_CRITICAL_FAILED=0
manifest: `agents/evals/report_quality_eval.toml`

| eval | item | status | critical | missing required | matched forbidden |
| --- | --- | --- | --- | --- | --- |
| `report-writing-runtime-skill` | `REPORT-RUNTIME-1` | `pass` | `yes` | `none` | `none` |
| `report-writing-runtime-skill` | `REPORT-RUNTIME-2` | `pass` | `yes` | `none` | `none` |
| `report-writing-runtime-skill` | `REPORT-RUNTIME-3` | `pass` | `yes` | `none` | `none` |
| `report-writing-runtime-skill` | `REPORT-RUNTIME-4` | `pass` | `yes` | `none` | `none` |
| `report-writing-human-doc` | `REPORT-CHECKLIST-1` | `pass` | `yes` | `none` | `none` |
| `report-writing-human-doc` | `REPORT-CHECKLIST-2` | `pass` | `yes` | `none` | `none` |
| `report-writing-human-doc` | `REPORT-CHECKLIST-3` | `pass` | `yes` | `none` | `none` |
| `report-writing-human-doc` | `REPORT-CHECKLIST-4` | `pass` | `yes` | `none` | `none` |
| `report-reviewer-route` | `REPORT-REVIEWER-1` | `pass` | `yes` | `none` | `none` |
