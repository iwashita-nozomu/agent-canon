---
name: pr-processing
description: "Use when processing GitHub pull requests or issue queues: inventory open PRs, preserve PR Essence in bodies and run bundles, resolve conflicts, order merges, update branch protection evidence, merge only with authority, triage stale issues, and sync AgentCanon source PRs with parent pin PRs."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"19ea4de36abd487a019f4538b710e480468d5a72d0cc720144f68dbb1299629e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes pr-processing for runtime discovery.
upstream design ../../../agents/skills/pr-processing.md owner
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
