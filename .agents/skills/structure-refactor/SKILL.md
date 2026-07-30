---
name: structure-refactor
description: "Use when repository structure review, repo-refactor requests, expected AgentCanon layout, directory responsibilities, canonical README ownership, path layout, root views, project .codex/.agents views, personal ~/.codex runtime boundaries, or responsibility-scope maps must be reviewed, repaired, or refactored using structure contracts, recursive directory README analysis, source/view ownership checks, stale-surface sweeps, dependency manifests, and behavior-preserving move/rename gates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:structure-refactor -->
<!-- canonical: agents/skills/structure-refactor.md sha256=2ffff618ad0987ecc7e0f7e3be15e38e45de483fbd272daa624d5cae60453145 -->
<!-- route: agents/skills/catalog.yaml#skill:structure-refactor.routing digest=3843a00e7ed048212731fe5ebfd8e8cbb1386f4437bf6e8ada773c84e534c447 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:structure-refactor digest=8d325ebb7ed34419da1c0d8b9f70f392b21c16394598f4f7c02598987cbb9752 -->
<!-- commands: agents/skills/catalog.yaml#skill:structure-refactor.tool_commands digest=06dbd083769e373fb23513270a69283bd44bdc65d6e7dd8fc1728b7fcf8f05a9 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/structure-refactor.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# structure-refactor

## Canonical Skill

Canonical workflow and policy: [structure-refactor](../../../agents/skills/structure-refactor.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill structure-refactor --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `06dbd083769e373fb23513270a69283bd44bdc65d6e7dd8fc1728b7fcf8f05a9`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
