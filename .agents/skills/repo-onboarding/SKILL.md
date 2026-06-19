---
name: repo-onboarding
description: Use when entering an unfamiliar repository or subdirectory and you need the fastest safe path to the repo overview, commands, conventions, and agent canon.
---
<!--
@dependency-start
contract skill
responsibility Documents Repo Onboarding for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Repo Onboarding

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill repo-onboarding --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `README.md`, `QUICK_START.md`, and `documents/README.md`.
1. Read `agents/workflows/README.md` and `docker/README.md` when workflow selection or container runtime matters.
1. Read `agents/README.md`.
1. If the active agent is Codex, read `agents/canonical/CODEX_WORKFLOW.md`.
1. Check `scripts/README.md` for commands.
1. If the task touches experiments, read `agents/workflows/experiment-workflow.md`.
1. If the task touches agents, read `agents/canonical/README.md`.
1. Summarize the repo shape before making changes.
