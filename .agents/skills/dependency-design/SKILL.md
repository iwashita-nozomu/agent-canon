---
name: dependency-design
description: "Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-design -->
<!-- canonical: agents/skills/dependency-design.md sha256=94f31aef4da72013fdb9ac61c5407f25546a5dc612fa743d5925322812441e80 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-design.routing digest=fd5d2c3a0fa886708e92ae247efd24e15b5f15d0aea9c1d07ee58fa49755de74 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-design digest=102ef25d019c6a191262ebeef4c65533b17b6a9680b60df32d2a7c411c5817a2 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-design.tool_commands digest=fd56b4d688eb0b9a3285dcfb324edd5b112e21077542bd32d3bb44de29bca88a -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/dependency-design.md
@dependency-end
-->

# dependency-design

## Canonical Skill

Canonical workflow and policy: [dependency-design](../../../agents/skills/dependency-design.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text`; schema `skill_tool_commands.v2`, digest: `fd56b4d688eb0b9a3285dcfb324edd5b112e21077542bd32d3bb44de29bca88a`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
