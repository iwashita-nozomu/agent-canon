---
name: pr-processing
description: "Use when processing GitHub pull requests or issue queues: inventory open PRs, preserve PR Essence in bodies and run bundles, resolve conflicts, order merges, update branch protection evidence, merge only with authority, triage stale issues, and sync AgentCanon source PRs with parent pin PRs."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:pr-processing -->
<!-- canonical: agents/skills/pr-processing.md sha256=220fd388ae070a110e20de0dfe0c32c949268f626ad2ad691175c3436e516635 -->
<!-- route: agents/skills/catalog.yaml#skill:pr-processing.routing digest=4a43623e00425e7a17ac09a698dc0a10620b1b5132f324301cc2c787aa59ab68 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:pr-processing digest=0ea9eac3476dae094ad8dcb6ad81cb1e80d77420bc6e108599c09c05f2f95c7b -->
<!-- commands: agents/skills/catalog.yaml#skill:pr-processing.tool_commands digest=34b44e2f9371055eac3f2caf7bf57d7492548d016e7f33aff38b7b82d498b96d -->
<!-- host-config: path=../.agents/skills/pr-processing/SKILL.md index=39 order=39 enabled=true digest=51649db0c121f75fa4e2aa50b98cd140bd0b9f33e730e2d0eb7298fcec7df3d0 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=80d7d43e3ac8fea6e5721d67090e115501307c7e72b9f0b4c45d219c75b5dcd3 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes pr-processing as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/pr-processing.md canonical skill owner
@dependency-end
-->

# pr-processing

## Canonical Skill

Canonical workflow and policy: [pr-processing](../../../agents/skills/pr-processing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill pr-processing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
