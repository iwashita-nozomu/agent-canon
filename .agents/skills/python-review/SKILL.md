---
name: python-review
description: Use when Python code changes need strict review for pyright, pytest, ruff, type boundaries, and API behavior.
---
<!--
@dependency-start
responsibility Documents Python Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Python Review

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill python-review --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/python-review.md`.
1. Fix the changed Python files and related tests before validating.
1. Run or inspect `pyright`.
1. Run or inspect `pytest tests/`.
1. Run or inspect `ruff check python tests --select D,E,F,I,UP --ignore E501`.
1. Check API behavior, type boundaries, and docs/test follow-through.
1. Report findings before summaries.
