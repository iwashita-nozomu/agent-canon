# Report Quality Eval Results

<!--
@dependency-start
responsibility Documents accumulated report quality eval result storage.
upstream design ../../README.md eval usage contract
upstream design ../../report_quality_eval.toml report quality eval manifest
downstream implementation ../../../../tools/agent_tools/evaluate_report_quality.py writes report quality eval reports
downstream implementation ../../../../tools/agent_tools/eval_accumulation_check.py validates accumulated report quality evidence
@dependency-end
-->

This directory stores append-only report quality eval reports produced by
`tools/agent_tools/evaluate_report_quality.py`.

The file name convention is:

```text
report-quality-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>-<pass|fail>.md
```

Each report records checklist-level pass/fail rows for the report-writing skill
and report reviewer routing surfaces. Reports do not store raw user prompts or
unbounded generated report text.
