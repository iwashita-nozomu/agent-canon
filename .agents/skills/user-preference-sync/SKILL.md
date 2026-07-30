---
name: user-preference-sync
description: "Use when memory/USER_PREFERENCES.md should be distilled into stable AGENTS.md preferences without carrying over task-local instructions."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:user-preference-sync -->
<!-- canonical: agents/skills/user-preference-sync.md sha256=037632daa77de3d214f4e936a407ef1139b1d671b059144a215899fe84808b5d -->
<!-- route: agents/skills/catalog.yaml#skill:user-preference-sync.routing digest=3eb5cd69e76e742532b465c4c680c619cc9abc036c9b57bf2beefba9139dd659 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:user-preference-sync digest=5113f4858ea6e5f5908a72dd70dae33d5ad1b81206103eaec3a0ed1dcf763c4d -->
<!-- commands: agents/skills/catalog.yaml#skill:user-preference-sync.tool_commands digest=3f1bb68455c515701c8ce1c15be4611c8b49ab6e45bea28230567d56cefbebdd -->
<!-- host-config: path=../.agents/skills/user-preference-sync/SKILL.md index=56 order=56 enabled=true digest=8ecdd9a5c5e40840f3e60c0406ffb2e866e9da25c087eb8cf3ef33bf9a29543e -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=0dcdbb0b4448ac3ac80462659bbea6a87b9739cdcde78c2de1b735fb9cbaf355 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/user-preference-sync.md
@dependency-end
-->

# user-preference-sync

## Canonical Skill

Canonical workflow and policy: [user-preference-sync](../../../agents/skills/user-preference-sync.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill user-preference-sync --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
