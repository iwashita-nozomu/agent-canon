---
name: computational-optimization
description: "Use when designing, implementing, reviewing, or diagnosing numerical optimization, solvers, preconditioners, convergence, gradients, Jacobians, Hessians, KKT conditions, tolerances, or optimization benchmarks; fixes the mathematical and validation contract before code or experiment changes."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:computational-optimization -->
<!-- canonical: agents/skills/computational-optimization.md sha256=0c70d53b1fc9100fcd6b1c1b8f7e63238bf6fdaffbeb9da0b8c42b9a56c16336 -->
<!-- route: agents/skills/catalog.yaml#skill:computational-optimization.routing digest=3cd1e4900875547f684079e08bf0383aca540e652b56f911493a9b7e4231b27f -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:computational-optimization digest=7513bdc9961d503677724d22a087ed8075b4e8e1c91a5f543cbb45e1d8264a4e -->
<!-- commands: agents/skills/catalog.yaml#skill:computational-optimization.tool_commands digest=f017a3cded113d914f275481c9203eddcd67eaee0a5fd48bc3e4915b3f5c37ea -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/computational-optimization.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# computational-optimization

## Canonical Skill

Canonical workflow and policy: [computational-optimization](../../../agents/skills/computational-optimization.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill computational-optimization --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `f017a3cded113d914f275481c9203eddcd67eaee0a5fd48bc3e4915b3f5c37ea`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
