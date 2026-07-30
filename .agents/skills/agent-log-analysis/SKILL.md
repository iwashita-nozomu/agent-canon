---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; first convert raw logs into a structured dashboard summary with AgentCanon source generate_agent_runtime_dashboard.py before reading or interpreting evidence."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-log-analysis -->
<!-- canonical: agents/skills/agent-log-analysis.md sha256=d5a25411820c7ef6690fa6d49d8508d066ac9f1f4d47019f5bc9c18e6e16d49e -->
<!-- route: agents/skills/catalog.yaml#skill:agent-log-analysis.routing digest=209982eafc56e4192bcf5be5bbea7741de5cbe6681ef255974b92fe16c89af3d -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-log-analysis digest=486745168c9797b58bfa8de909ac43bc81c349067f2a4fd6e10f889a214dacc9 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-log-analysis.tool_commands digest=151008baca402245187208c3ecab550464e0a5673309b3dc880c88c0a2c884c0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/agent-log-analysis.md
@dependency-end
-->

# agent-log-analysis

## Canonical Skill

Canonical workflow and policy: [agent-log-analysis](../../../agents/skills/agent-log-analysis.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-log-analysis --format text`; schema `skill_tool_commands.v2`, digest: `151008baca402245187208c3ecab550464e0a5673309b3dc880c88c0a2c884c0`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
