---
name: literature-survey
description: "Use when a task needs paper search, prior-art mapping, contradictory-source hunting, or a reusable bibliography."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:literature-survey -->
<!-- canonical: agents/skills/literature-survey.md sha256=399a3f45c3075bd847ac006ae35579bf98be12f42cead46b06d8c4df10803750 -->
<!-- route: agents/skills/catalog.yaml#skill:literature-survey.routing digest=d4f4cf4a983780461a4267d1cbd74b267b0b2595afe2e206796f068577da7df3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:literature-survey digest=fa83085b0c4dcab7ecbec02f8fc20fadb3a52c3e8858462177b53cbe99d5b90f -->
<!-- commands: agents/skills/catalog.yaml#skill:literature-survey.tool_commands digest=a43d722eedba0cb2e2736239f1b916ab19b5c5d873852a36451c09bc37957473 -->
<!-- host-config: path=../.agents/skills/literature-survey/SKILL.md index=31 order=31 enabled=true digest=6d264c903e463a7c36df0c9b9b49f784c79a07155aa816d7ce2206699f765bf3 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=921bfba5bc60695c6e567789be5507c64fa087dafff91ecfca8eb5a4582fa60f -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes literature-survey as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/literature-survey.md canonical skill owner
@dependency-end
-->

# literature-survey

## Canonical Skill

Canonical workflow and policy: [literature-survey](../../../agents/skills/literature-survey.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill literature-survey --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
