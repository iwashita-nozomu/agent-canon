---
name: document-canon-cleanup
description: "Use when organizing repository documents, finding non-canonical docs, separating source canon from generated reports, eval results, closed issues, duplicate headings, or stale document paths."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"e4b1f72fd80e2a9817912e6511c0fa753a9dfdfb5d34bd158a2df447cb3dc5a1"} -->

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
