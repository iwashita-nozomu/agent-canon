<!--
@dependency-start
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../canonical/skills.md skill canon registry
downstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py runs these evals
@dependency-end
-->

# Skill And Workflow Prompt Evals

This directory stores deterministic eval definitions for agent-facing skills and workflows.
Each eval is a frozen checklist for one prompt surface or one glob-expanded prompt family.
The default manifest covers all discoverable skill shims, all human-facing skill docs, and all workflow docs.
Add narrower eval entries when a specific skill or workflow needs stronger invariants.

Use these evals when changing a skill, workflow, or routing prompt:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml
```

An eval passes only when every critical checklist item passes.
If an eval reports drift, fix the target prompt and rerun the same manifest until the report passes.
