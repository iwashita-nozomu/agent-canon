---
name: literature-survey
description: Use when a task needs paper search, prior-art mapping, contradictory-source hunting, or a reusable bibliography.
---
<!--
@dependency-start
contract skill
responsibility Documents Literature Survey for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/prose-reasoning-graph.md defines claim/evidence graph handoffs
@dependency-end
-->


# Literature Survey

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill literature-survey --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/literature-survey.md`.
1. Read `agents/workflows/workflow-references.md`.
1. Fix the question, scope, and exclusion criteria before searching.
1. Before web search, PDF download, or citation lookup, inspect existing `references/`, `notes/`, `documents/`, and topic reports for the same source or claim. Reuse or update the existing source note instead of creating a parallel truth surface.
1. Prefer primary sources, surveys, benchmark comparison papers, and official docs over tertiary summaries.
1. Record contrary or scope-limiting evidence, not only supporting sources.
1. If a prose graph handoff is present, use unsupported-claim and citation/evidence-gap diagnostics to seed query terms, source adoption decisions, and source exclusion checks.
1. If a source is used, downloaded, quoted, or cited in the answer/report, leave a durable tracked reference note or source packet with URL/DOI, access date, claim used, limitation, and artifact location; do not rely on transient browser context as the only record.
