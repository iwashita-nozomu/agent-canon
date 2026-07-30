---
name: result-artifact-writeout
description: "Use when writing, exporting, saving, accumulating, or reporting tool/checker/hook/skill/eval/experiment results; creates durable raw and summary artifacts with unique IDs and no accidental overwrite."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:result-artifact-writeout -->
<!-- canonical: agents/skills/result-artifact-writeout.md sha256=7746950a045324e7111da78c984fce9d5ddb51d38454a8818c08038baa08d1f5 -->
<!-- route: agents/skills/catalog.yaml#skill:result-artifact-writeout.routing digest=8a4143d9c15cedf7e6cbad6214ddf32cd1cba61b4d05aea0024796dc408672f4 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:result-artifact-writeout digest=26849f81147b6da479bf5b6819810a493d05e05efb12fb99bded671b1f649d4f -->
<!-- commands: agents/skills/catalog.yaml#skill:result-artifact-writeout.tool_commands digest=fb71b0640c95875b34ecde5a661ad661e31aa790cf182fd83fd79744d3b7f189 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/result-artifact-writeout.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# result-artifact-writeout

## Canonical Skill

Canonical workflow and policy: [result-artifact-writeout](../../../agents/skills/result-artifact-writeout.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill result-artifact-writeout --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `fb71b0640c95875b34ecde5a661ad661e31aa790cf182fd83fd79744d3b7f189`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
