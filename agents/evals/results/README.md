# Eval Results

<!--
@dependency-start
responsibility Documents accumulated AgentCanon eval result storage.
upstream design ../README.md eval directory contract
downstream design skill-workflow-prompt/README.md skill prompt eval result naming convention
downstream design hook-runs/README.md hook result naming convention
downstream design local-llm-responsibility/README.md local LLM eval result naming convention
downstream implementation ../../../tools/agent_tools/eval_accumulation_check.py validates accumulated result evidence
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
- `local-llm-responsibility/`: single-file local LLM responsibility eval
  reports produced by `local_llm_eval.py`. Prompt-only runs are the default;
  model-backed runs are optional and never become repo-wide CI authority.

Validate the accumulated evidence before using it as workflow feedback:

```bash
python3 tools/agent_tools/eval_accumulation_check.py --root .
```

The checker is structural. It accepts legacy readable reports, but namespaced
new hook logs must carry the required fields documented under `hook-runs/`.
