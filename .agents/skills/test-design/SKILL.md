---
name: test-design
description: "Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:test-design -->
<!-- canonical: agents/skills/test-design.md sha256=309028d23de762a22de6c627ac87f256ac8edf3a569c6e30db1fa542e80c4352 -->
<!-- route: agents/skills/catalog.yaml#skill:test-design.routing digest=49dd312bd2d10ce4758f4d5adb13180c50c2a60f73d4880b0538dc3a47f651d3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:test-design digest=ab8ae849289317fe7c67f4fe4b20109754d2b80aa7603cf6dc5b33da4bd26cbe -->
<!-- commands: agents/skills/catalog.yaml#skill:test-design.tool_commands digest=2fb5ea1fc782726bef51e7b4ddd0143f9a4cfee68b9b08fee834eeb169bf963f -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/test-design.md
@dependency-end
-->

# test-design

## Canonical Skill

Canonical workflow and policy: [test-design](../../../agents/skills/test-design.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill test-design --format text`; schema `skill_tool_commands.v2`, digest: `2fb5ea1fc782726bef51e7b4ddd0143f9a4cfee68b9b08fee834eeb169bf963f`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
