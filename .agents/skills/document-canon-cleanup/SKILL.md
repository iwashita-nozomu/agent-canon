---
name: document-canon-cleanup
description: "Use when organizing repository documents, finding non-canonical docs, separating source canon from generated reports, eval results, closed issues, duplicate headings, or stale document paths."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"6978fa9976449a8a2f7df57a58b5691a69e390449f7d60ace4530a4e4d724c5e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes document-canon-cleanup for runtime discovery.
upstream design ../../../agents/skills/document-canon-cleanup.md owner
@dependency-end
-->

# document-canon-cleanup

## Canonical Skill

Canonical workflow and policy: [document-canon-cleanup](../../../agents/skills/document-canon-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill document-canon-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
