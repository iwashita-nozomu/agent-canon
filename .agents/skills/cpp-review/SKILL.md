---
name: cpp-review
description: Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior.
---
<!--
@dependency-start
contract skill
responsibility Documents C++ Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# C++ Review

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill cpp-review --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/cpp-review.md`.
1. Fix the changed native files, headers, and related tests before validating.
1. Run or inspect the project-native configure, build, and test commands.
1. If the repo uses CMake, run or inspect `cmake -S . -B build`, `cmake --build build`, and `ctest --test-dir build`.
1. Check ABI boundaries, header drift, ownership, error paths, and docs/test follow-through.
1. Report findings before summaries.
