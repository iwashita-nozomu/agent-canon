---
name: html-output
description: "Use when the user explicitly asks for HTML output, a browser-readable page, dashboard/report HTML, external browser publication, or local preview server; defaults reports to Markdown unless HTML is explicit."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:html-output -->
<!-- canonical: agents/skills/html-output.md sha256=3743668c77956ea0368326287a6759d76a4b824a09a0b4fd1b0873f32d88e1b0 -->
<!-- route: agents/skills/catalog.yaml#skill:html-output.routing digest=a3724897179885d50f35b9cdca676b197d9285abb4b36f33cd75806e24316a63 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:html-output digest=63c8377b1a4ef67c4612aaf6be6beb92d8c14827bdfc0447f1cc3b518e2e0047 -->
<!-- commands: agents/skills/catalog.yaml#skill:html-output.tool_commands digest=faae41417745d693597e5c01a9099bc454cc545f36c3d81acdcabc13d57190ff -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/html-output.md
@dependency-end
-->

# html-output

## Canonical Skill

Canonical workflow and policy: [html-output](../../../agents/skills/html-output.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill html-output --format text`; schema `skill_tool_commands.v2`, digest: `faae41417745d693597e5c01a9099bc454cc545f36c3d81acdcabc13d57190ff`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
