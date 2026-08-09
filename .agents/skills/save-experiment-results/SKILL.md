---
name: save-experiment-results
description: "Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"fe5a8b13af36d44ef2925f20fa99b0186926752ef2b472385c5085b5c5d6c391"} -->

<!--
@dependency-start
contract skill
responsibility Exposes save-experiment-results for runtime discovery.
upstream design ../../../agents/skills/save-experiment-results.md owner
@dependency-end
-->

# save-experiment-results

## Canonical Skill

Canonical workflow and policy: [save-experiment-results](../../../agents/skills/save-experiment-results.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill save-experiment-results --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
