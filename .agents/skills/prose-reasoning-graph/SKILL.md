---
name: prose-reasoning-graph
description: "Use when existing prose should be converted into a SQLite-backed structure graph, diagnosed for discourse/argument/evidence/experiment gaps, explained in natural language, and handed off to writing or review skills with split/merge/bridge/reorder rewrite packets."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:prose-reasoning-graph -->
<!-- canonical: agents/skills/prose-reasoning-graph.md sha256=45728c582df1b39f818e2e6ac5bf2a56cbc2278c036304f176dd5be8f1cdb508 -->
<!-- route: agents/skills/catalog.yaml#skill:prose-reasoning-graph.routing digest=b750d3bf38d9fd351ec65b811d9c33ede2668d50c735670f53c15c5ce611df38 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:prose-reasoning-graph digest=d56c3955f3c177216a9feba7502f8ae837e83c92189473870a1fa55ed96e03d7 -->
<!-- commands: agents/skills/catalog.yaml#skill:prose-reasoning-graph.tool_commands digest=f0ddeb9286700bbed40ce26d0944391506efae5e1d8277c68958a2b31cf955cf -->
<!-- host-config: path=../.agents/skills/prose-reasoning-graph/SKILL.md index=38 order=38 enabled=true digest=dbe642d512e8d6814d3a94ab57e8bb0398a8ccd633834d0b00f78c37c89945e8 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=1bd7678f3ff87fa82c6921279feef5961417a742a523bb2ab85749629403a3b0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes prose-reasoning-graph for runtime discovery.
upstream design ../../../agents/skills/prose-reasoning-graph.md owner
@dependency-end
-->

# prose-reasoning-graph

## Canonical Skill

Canonical workflow and policy: [prose-reasoning-graph](../../../agents/skills/prose-reasoning-graph.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill prose-reasoning-graph --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
