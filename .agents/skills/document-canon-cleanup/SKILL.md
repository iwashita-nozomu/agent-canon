---
name: document-canon-cleanup
description: "Use when organizing repository documents, finding non-canonical docs, separating source canon from generated reports, eval results, closed issues, duplicate headings, or stale document paths."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"610c6a4622d045df48375facbd3d7f1822e2e17a50b5c5898fbfe145ec8bf658"} -->

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
