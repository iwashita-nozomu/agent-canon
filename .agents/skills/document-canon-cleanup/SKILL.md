---
name: document-canon-cleanup
description: "Use when organizing repository documents, finding non-canonical docs, separating source canon from generated reports, eval results, closed issues, duplicate headings, or stale document paths."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:document-canon-cleanup -->
<!-- canonical: agents/skills/document-canon-cleanup.md sha256=da83b14f573de3b6fe946042f0d88d07a142b17217904387892ffcfd05279168 -->
<!-- route: agents/skills/catalog.yaml#skill:document-canon-cleanup.routing digest=11a5decf86b437fd0be781e15800a78a4dbbff462a61b0e477ef08dcc7db5abe -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:document-canon-cleanup digest=0bde774c2d8bcc77e63b276624588393c4eaf7245055659ff4552ac27d319d8e -->
<!-- commands: agents/skills/catalog.yaml#skill:document-canon-cleanup.tool_commands digest=5d9419d822d769e9777136685afd64d61d7305f3baf2eb73aa37b485250182af -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/document-canon-cleanup.md
@dependency-end
-->

# document-canon-cleanup

## Canonical Skill

Canonical workflow and policy: [document-canon-cleanup](../../../agents/skills/document-canon-cleanup.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill document-canon-cleanup --format text`; schema `skill_tool_commands.v2`, digest: `5d9419d822d769e9777136685afd64d61d7305f3baf2eb73aa37b485250182af`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
