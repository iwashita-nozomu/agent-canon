---
name: experiment-lifecycle
description: "Use this skill when preparing, running, or validating experiments."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:experiment-lifecycle -->
<!-- canonical: agents/skills/experiment-lifecycle.md sha256=81c9a387fcfb327b77af99fc6302e99376bbe5f1735446fa00b5cca99ded1cfe -->
<!-- route: agents/skills/catalog.yaml#skill:experiment-lifecycle.routing digest=920be5167b67012e02c6f64d6b571627479c25d3d63508cb6d088156e8427f00 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:experiment-lifecycle digest=03b4becafba4dd8a413e7c1848787007db27190f8fa70d49033f96eaeab08c94 -->
<!-- commands: agents/skills/catalog.yaml#skill:experiment-lifecycle.tool_commands digest=7742e6a4e3c0946ee9c11db194e928993d3a4376d3accb03da65509d7fa21590 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/experiment-lifecycle.md
@dependency-end
-->

# experiment-lifecycle

## Canonical Skill

Canonical workflow and policy: [experiment-lifecycle](../../../agents/skills/experiment-lifecycle.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-lifecycle --format text`; schema `skill_tool_commands.v2`, digest: `7742e6a4e3c0946ee9c11db194e928993d3a4376d3accb03da65509d7fa21590`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
