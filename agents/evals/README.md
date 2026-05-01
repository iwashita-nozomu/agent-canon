<!--
@dependency-start
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../canonical/skills.md skill canon registry
downstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py runs these evals
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py runs behavior evals
@dependency-end
-->

# Skill And Workflow Prompt Evals

This directory stores deterministic eval definitions for agent-facing skills, workflows, and
run-bundle behavior evidence.
Prompt evals are frozen checklists for one prompt surface or one glob-expanded prompt family.
Behavior evals are frozen criteria for observable agent actions recorded in run artifacts.
The default prompt manifest covers all discoverable skill shims, all human-facing skill docs,
and all workflow docs. Add narrower eval entries when a specific skill or workflow needs
stronger invariants.

Use these evals when changing a skill, workflow, or routing prompt:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml
```

An eval passes only when every critical checklist item passes.
If an eval reports drift, fix the target prompt and rerun the same manifest until the report passes.

Use behavior evals before closeout to check that skills and workflows changed actual agent
behavior, not only text:

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest agents/evals/agent_behavior_eval.toml \
  --write
```

Behavior evals inspect `workflow_monitoring.md`, `agent_evaluation.md`, review artifacts,
closeout evidence, and validation logs. They require observable events such as skill invocation,
subagent routing, tool gates, prompt eval runs, feedback resolution, subagent lifecycle closeout,
and diff-check decisions. Record these events during the run with
`tools/agent_tools/workflow_monitor.py --behavior-event "..."` instead of reconstructing them only
at closeout.
