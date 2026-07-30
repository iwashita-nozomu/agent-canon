---
name: dependency-analysis
description: "Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-analysis -->
<!-- canonical: agents/skills/dependency-analysis.md sha256=539092d1120f07d4d790612bce3cfe80dd6d3f8c4e55b1142d36dfbb2f2b1f45 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-analysis.routing digest=16584206a3b7cd1747d112850220a0c705bf7f156d5aea6d9152b029b5ff8819 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-analysis digest=87001901117d908accf231c34b624bd8663bc562ce1f4f78bba0700317f90ac7 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-analysis.tool_commands digest=9035a06f63e5220d9d3b3e5f98860ad298e100d793ecefed579d1e7f8aeeff7c -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/dependency-analysis.md
@dependency-end
-->

# dependency-analysis

## Canonical Skill

Canonical workflow and policy: [dependency-analysis](../../../agents/skills/dependency-analysis.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-analysis --format text`; schema `skill_tool_commands.v2`, digest: `9035a06f63e5220d9d3b3e5f98860ad298e100d793ecefed579d1e7f8aeeff7c`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
