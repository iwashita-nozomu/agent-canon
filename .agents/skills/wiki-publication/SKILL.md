---
name: wiki-publication
description: "Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:wiki-publication -->
<!-- canonical: agents/skills/wiki-publication.md sha256=9f83f747726d605400e4180da5f8d68d5828a3af47797f29870cfb40fef52d8c -->
<!-- route: agents/skills/catalog.yaml#skill:wiki-publication.routing digest=5dad8bcc880ca607eee2a53db930c5162f3a0c1f49169bbaed2ea5e15a559909 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:wiki-publication digest=99168c55688c0e24c5211e38865ad558a1d1dfcc073db7941116a921456eaf9f -->
<!-- commands: agents/skills/catalog.yaml#skill:wiki-publication.tool_commands digest=860e234ccbcaa0ed9d3ea41c8bc668f910ba5ed4b02c930fa122424f75b3fd7e -->
<!-- host-config: path=../.agents/skills/wiki-publication/SKILL.md index=58 order=58 enabled=true digest=7b386bf9576224a68550e04ca96f3c5a495f43c3a433919eee547306402c9ecc -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=2eaf5b295eaf8f193243bbe650711012f5ba5853b0bf6b7f8c79b91aa110d93d -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes wiki-publication as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/wiki-publication.md canonical skill owner
@dependency-end
-->

# wiki-publication

## Canonical Skill

Canonical workflow and policy: [wiki-publication](../../../agents/skills/wiki-publication.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill wiki-publication --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
