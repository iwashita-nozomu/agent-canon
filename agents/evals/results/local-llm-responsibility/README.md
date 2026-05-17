# Local LLM Responsibility Eval Results

<!--
@dependency-start
responsibility Documents append-only local LLM responsibility eval results.
upstream design ../../README.md eval directory contract
upstream design ../../local_llm_responsibility_eval.toml local LLM eval manifest
downstream implementation ../../../../tools/agent_tools/local_llm_eval.py writes result reports
downstream implementation ../../../../tools/agent_tools/eval_accumulation_check.py validates result accumulation
@dependency-end
-->

This directory stores accumulated results from `local_llm_eval.py`.

The current Local LLM scope is deliberately narrow: single-file responsibility
analysis only. The harness can run prompt-boundary evals without a model, and
can optionally run the configured local model when `--run-llm` is supplied.
Neither path grants CI pass/fail authority for repo-wide ownership.

Result file names use:

```text
local-llm-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>-<pass|fail|skip>.md
```

Do not overwrite old reports. Each measurement gets a new run id.
