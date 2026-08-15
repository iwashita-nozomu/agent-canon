---
name: save-experiment-results
description: "Retain one experiment result as one deterministic git-annex archive. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, verify its manifest/report, prevent overwrites, or retain failed/partial artifacts."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"a849d6edac8dad67f9858a7718479705061dd0f582be8bd07cf3276210a28271"} -->

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
