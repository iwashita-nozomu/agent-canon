---
name: owner-bounded-routing
description: "Use for owner-bounded repository edits after routing evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior/schema expansion; also use for typo/link/format-only edits and Owner-Bounded Change work where Codex should run existing tools directly, record owner/tool/validation evidence, keep validation targeted, and avoid escalating to broad workflow prose."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:owner-bounded-routing -->
<!-- canonical: agents/skills/owner-bounded-routing.md sha256=b91114a26c3137132d728630460fb861ef5772632c327d0ce0917f304db0653e -->
<!-- route: agents/skills/catalog.yaml#skill:owner-bounded-routing.routing digest=f7a555da339b2fd491fcd1139f994324d489d9f17e2352d20efcd8cd0201f0b6 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:owner-bounded-routing digest=78734376c281b296991698dabce3c5ff736e7714e8024ed05981d8aa2fd90f27 -->
<!-- commands: agents/skills/catalog.yaml#skill:owner-bounded-routing.tool_commands digest=35b4a5c022a081c53a5b25a644a6287a8d4f1d72eb6e9d5f6779af12f2b910c0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/owner-bounded-routing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# owner-bounded-routing

## Canonical Skill

Canonical workflow and policy: [owner-bounded-routing](../../../agents/skills/owner-bounded-routing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill owner-bounded-routing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `35b4a5c022a081c53a5b25a644a6287a8d4f1d72eb6e9d5f6779af12f2b910c0`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
