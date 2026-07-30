---
name: python-review
description: "Python 差分を pyright、pytest、ruff、型境界、API 挙動、OOP 可読性根拠で厳密に確認する。"
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:python-review -->
<!-- canonical: agents/skills/python-review.md sha256=ebdea2d7e5ec98def4575f493511371eb4f964beea1c948fd9ff1ac182a48d54 -->
<!-- route: agents/skills/catalog.yaml#skill:python-review.routing digest=dec871082200bc4101743c885db4dd5ab7bc2b542dae384ed27de1e9d43163a3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:python-review digest=c37e7ae69dfd399de98e56f124b5fec38636d08137a9334d869130ff86e80927 -->
<!-- commands: agents/skills/catalog.yaml#skill:python-review.tool_commands digest=6e43fb40b59c525a46458a6801970ed9ecdcdef353861afb50699c680205a871 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/python-review.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# python-review

## Canonical Skill

Canonical workflow and policy: [python-review](../../../agents/skills/python-review.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill python-review --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `6e43fb40b59c525a46458a6801970ed9ecdcdef353861afb50699c680205a871`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
