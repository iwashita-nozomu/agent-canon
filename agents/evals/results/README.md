# Eval Results

<!--
@dependency-start
responsibility Documents accumulated AgentCanon eval result storage.
upstream design ../README.md eval directory contract
downstream design skill-workflow-prompt/README.md skill prompt eval result naming convention
downstream design hook-runs/README.md hook result naming convention
@dependency-end
-->

This directory stores detailed eval outputs that AgentCanon keeps as durable
evidence across runs.

Do not overwrite result files. Eval tools assign a unique run id for each
measurement and write a new file. Periodic cleanup can compact or archive old
results, but day-to-day agent runs append new evidence instead of replacing the
last report.

Current result families:

- `skill-workflow-prompt/`: prompt evals produced when a skill or workflow
  prompt is used, changed, or repaired.
- `hook-runs/`: Codex hook outcomes accumulated with unique `hook_run_id`
  values so PR / push guide generation can group repeated failures without
  overwriting raw events.
