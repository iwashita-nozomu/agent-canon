---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:worktree-health -->
<!-- canonical: agents/skills/worktree-health.md sha256=10be647ab1931df66328b84c1e2efd8c5c2edd9ccff67b445c55f06aab53e0c3 -->
<!-- route: agents/skills/catalog.yaml#skill:worktree-health.routing digest=41008a69c6a7d7b76c1fd6936f8d71b5679989941c22c539fea30650d599c618 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:worktree-health digest=b67e161607cfc64bcf70b226f7f0c3b565b202e85549ed98891d6b3eeb37953a -->
<!-- commands: agents/skills/catalog.yaml#skill:worktree-health.tool_commands digest=c5283caf842efa698e152c575e6441a789c002778782ad9284c9d4178c0c70b4 -->
<!-- host-config: path=../.agents/skills/worktree-health/SKILL.md index=57 order=57 enabled=true digest=c9412634358e928f06f3272452702f0c21cb5de4147c8bbeb047067fdb7923ee -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=c2f793560a3a717425a28a6eeca8f27bbbe3281c0dbaf3f7ad54db18effc6cb4 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes worktree-health for runtime discovery.
upstream design ../../../agents/skills/worktree-health.md owner
@dependency-end
-->

# worktree-health

## Canonical Skill

Canonical workflow and policy: [worktree-health](../../../agents/skills/worktree-health.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-health --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
