---
name: structure-refactor
description: "Use when repository structure review, repo-refactor requests, expected AgentCanon layout, directory responsibilities, canonical README ownership, path layout, root views, project .codex/.agents views, personal ~/.codex runtime boundaries, or responsibility-scope maps must be reviewed, repaired, or refactored using structure contracts, recursive directory README analysis, source/view ownership checks, stale-surface sweeps, dependency manifests, and behavior-preserving move/rename gates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:structure-refactor -->
<!-- canonical: agents/skills/structure-refactor.md sha256=2a2d92fdc92e7976c835c8bc177e0a07bd1fc724721e0d7786105dc165b9957c -->
<!-- route: agents/skills/catalog.yaml#skill:structure-refactor.routing digest=3843a00e7ed048212731fe5ebfd8e8cbb1386f4437bf6e8ada773c84e534c447 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:structure-refactor digest=8d325ebb7ed34419da1c0d8b9f70f392b21c16394598f4f7c02598987cbb9752 -->
<!-- commands: agents/skills/catalog.yaml#skill:structure-refactor.tool_commands digest=e218e89fb461512b16bd28f18fe91de4cb9b1c78d7b53176a346f59cfea3cc90 -->
<!-- host-config: path=../.agents/skills/structure-refactor/SKILL.md index=50 order=50 enabled=true digest=0d0f31c01a0fcb1202cfa0d16440c329173225a63725d3e57fe68f3c893ab8a0 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=53ac9d2f2ce4cf84c2c6bf052632641fe4303fa38c89d8fd2d7c3eebc9aa958c -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes structure-refactor for runtime discovery.
upstream design ../../../agents/skills/structure-refactor.md owner
@dependency-end
-->

# structure-refactor

## Canonical Skill

Canonical workflow and policy: [structure-refactor](../../../agents/skills/structure-refactor.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill structure-refactor --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
