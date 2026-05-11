# Skill Workflow Prompt Eval Results

<!--
@dependency-start
responsibility Documents accumulated skill/workflow prompt eval result naming.
upstream design ../../README.md prompt eval directory contract
upstream implementation ../../../../tools/agent_tools/evaluate_skill_workflow_prompts.py writes unique reports
@dependency-end
-->

Every skill use must have prompt-eval measurement evidence. The detailed output
is accumulated here when the runner is called with `--accumulate`.

## File Naming

Accumulated files use this convention:

```text
<eval_run_id>-<status>-<skill-slug>.md
```

`eval_run_id` is assigned by
`tools/agent_tools/evaluate_skill_workflow_prompts.py` and has this form:

```text
skill-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>
```

The timestamp gives chronological order. The hash is derived from the eval
manifest path, run id, used skill list, and creation timestamp. If an explicitly
requested report path already exists, the tool writes a sibling file with the
same `eval_run_id` appended instead of overwriting the existing file.

`status` is `pass` or `fail`, and `skill-slug` is the dash-joined list passed
with `--skill-used`; `no-skill` is reserved for baseline checks that were not
attached to a concrete skill invocation.

## Required Invocation

For a run that uses skills, record both the accumulated report and run-local
behavior evidence:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml \
  --accumulate \
  --run-id <run-id> \
  --skill-used agent-orchestration \
  --skill-used codex-task-workflow
```

Then copy the emitted `EVAL_RUN_ID`, `EVAL_STATUS`, and
`EVAL_ACCUMULATED_REPORT` lines into `workflow_monitoring.md` with
`workflow_monitor.py --behavior-event`.
