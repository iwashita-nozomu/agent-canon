---
name: research-workflow
description: Use when a task needs external research, comparison design, iterative implementation and runs, and explicit review decisions before claims are accepted.
---
<!--
@dependency-start
contract skill
responsibility Documents Research Workflow for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Research Workflow

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill research-workflow --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/research-workflow.md`.
1. Read `agents/workflows/research-workflow.md`.
1. Resolve AgentCanon document paths relative to the AgentCanon source root. From a template or derived repo root, read `vendor/agent-canon/documents/experiment-critical-review.md`; from standalone AgentCanon, read `documents/experiment-critical-review.md`.
1. If the task includes paper search or prior-art mapping, also read `agents/skills/literature-survey.md`.
1. Fix the question, comparison targets, and exit criteria before implementing.
1. Before using external references, inspect existing repo reference notes and leave or update a durable source packet; claims based on browser/download context alone are not accepted.
1. Keep one change per loop iteration.
1. Do not close the loop while `report_rewrite_required`, `extra_validation_required`, or `rerun_required` remains.
