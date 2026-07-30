---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:worktree-health -->
<!-- canonical: agents/skills/worktree-health.md sha256=cdcc07f2f13e8a4328c791b3b2940b4fffc160a9945cc4539d2b6bc49877e3d5 -->
<!-- route: agents/skills/catalog.yaml#skill:worktree-health.routing digest=41008a69c6a7d7b76c1fd6936f8d71b5679989941c22c539fea30650d599c618 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:worktree-health digest=b67e161607cfc64bcf70b226f7f0c3b565b202e85549ed98891d6b3eeb37953a -->
<!-- commands: agents/skills/catalog.yaml#skill:worktree-health.tool_commands digest=c5283caf842efa698e152c575e6441a789c002778782ad9284c9d4178c0c70b4 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/worktree-health.md
@dependency-end
-->

# worktree-health

## Canonical Skill

Canonical workflow and policy: [worktree-health](../../../agents/skills/worktree-health.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-health --format text`; schema `skill_tool_commands.v2`, digest: `c5283caf842efa698e152c575e6441a789c002778782ad9284c9d4178c0c70b4`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
