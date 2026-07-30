---
name: issue-finding-report
description: "Use when converting accumulated prompt history, run bundles, hook logs, skill/tool/workflow routing evidence, eval summaries, or agent reports into durable AgentCanon skill issues; groups repeated evidence by abstract cause, shards multi-agent review by evidence partition, and writes issue candidates from structured dashboard artifacts."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:issue-finding-report -->
<!-- canonical: agents/skills/issue-finding-report.md sha256=60ebacc27cfa660c7320c86d72e6fdbd10ea1a45c1544413da139e4e125d0041 -->
<!-- route: agents/skills/catalog.yaml#skill:issue-finding-report.routing digest=d01425d3348c8a4cc2c977fc5c7ca5d33f22bf8dcccf1265643bf080af8cd324 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:issue-finding-report digest=1099d4384784263924e56b8198ee072577339839fb7b3ea5652b2ba1fc752efc -->
<!-- commands: agents/skills/catalog.yaml#skill:issue-finding-report.tool_commands digest=750477d8ef7f41ff2ed2004543fcc666b2e1de9d49f300fb7faef73e6fee04da -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/issue-finding-report.md
@dependency-end
-->

# issue-finding-report

## Canonical Skill

Canonical workflow and policy: [issue-finding-report](../../../agents/skills/issue-finding-report.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill issue-finding-report --format text`; schema `skill_tool_commands.v2`, digest: `750477d8ef7f41ff2ed2004543fcc666b2e1de9d49f300fb7faef73e6fee04da`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
