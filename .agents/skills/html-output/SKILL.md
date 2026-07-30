---
name: html-output
description: "Use when the user explicitly asks for HTML output, a browser-readable page, dashboard/report HTML, external browser publication, or local preview server; defaults reports to Markdown unless HTML is explicit."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:html-output -->
<!-- canonical: agents/skills/html-output.md sha256=4998532c5469908e96a74eb76448605d1a75d5be73c0c84c99158df74c01cbd9 -->
<!-- route: agents/skills/catalog.yaml#skill:html-output.routing digest=a3724897179885d50f35b9cdca676b197d9285abb4b36f33cd75806e24316a63 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:html-output digest=63c8377b1a4ef67c4612aaf6be6beb92d8c14827bdfc0447f1cc3b518e2e0047 -->
<!-- commands: agents/skills/catalog.yaml#skill:html-output.tool_commands digest=faae41417745d693597e5c01a9099bc454cc545f36c3d81acdcabc13d57190ff -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/html-output.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# html-output

## Canonical Skill

Canonical workflow and policy: [html-output](../../../agents/skills/html-output.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill html-output --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `faae41417745d693597e5c01a9099bc454cc545f36c3d81acdcabc13d57190ff`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
