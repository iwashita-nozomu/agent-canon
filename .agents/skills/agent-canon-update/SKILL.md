---
name: agent-canon-update
description: "Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-canon-update -->
<!-- canonical: agents/skills/agent-canon-update.md sha256=71c5a790e90e2a0b78b4be2a95264aa59bf6ad26895bbc03f03813525178727e -->
<!-- route: agents/skills/catalog.yaml#skill:agent-canon-update.routing digest=4ba74601f6db489caeb39270fe520ace1621e68f68b8848d97103b8ee2103614 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-canon-update digest=674cd72a8044b4c5520f0208a04f7bcd191f318bacfe9141c69567653f263692 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-canon-update.tool_commands digest=5561d7685a1445cf68ac6b40a4da47f9793a4d0d8749e243a1026da0ab259295 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/agent-canon-update.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# agent-canon-update

## Canonical Skill

Canonical workflow and policy: [agent-canon-update](../../../agents/skills/agent-canon-update.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `5561d7685a1445cf68ac6b40a4da47f9793a4d0d8749e243a1026da0ab259295`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
