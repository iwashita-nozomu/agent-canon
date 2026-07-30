---
name: save-experiment-results
description: "Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:save-experiment-results -->
<!-- canonical: agents/skills/save-experiment-results.md sha256=9fe6211ab4e21a0580b372d3991927211f1aa343b4061c2d50a307ebd5dea1e4 -->
<!-- route: agents/skills/catalog.yaml#skill:save-experiment-results.routing digest=e7e6280de33c4d5de334534d96aafeba109d07e8d74a991011280cd421cb98c5 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:save-experiment-results digest=539cd7169bf4ed079238078c3fa60d4cdde46f613832f05a11281d4b04febd40 -->
<!-- commands: agents/skills/catalog.yaml#skill:save-experiment-results.tool_commands digest=82ead84c462ffbe69d203d7752820b2bce4a486d2539fd51b5b0e2a4c41bb633 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/save-experiment-results.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# save-experiment-results

## Canonical Skill

Canonical workflow and policy: [save-experiment-results](../../../agents/skills/save-experiment-results.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill save-experiment-results --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `82ead84c462ffbe69d203d7752820b2bce4a486d2539fd51b5b0e2a4c41bb633`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
