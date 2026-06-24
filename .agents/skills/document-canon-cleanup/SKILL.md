---
name: document-canon-cleanup
description: Use when organizing repository documents, finding non-canonical docs, separating source canon from generated reports, eval results, closed issues, duplicate headings, or stale document paths.
---
<!--
@dependency-start
contract skill
responsibility Documents Document Canon Cleanup for this repository.
upstream design ../../../agents/skills/document-canon-cleanup.md human-facing skill canon
upstream implementation ../../../rust/agent-canon/src/structured_analysis.rs canonical document inventory implementation
@dependency-end
-->


# Document Canon Cleanup

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill document-canon-cleanup --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/document-canon-cleanup.md`.
1. Prefer the Rust structured-analysis command:

```bash
agent-canon structured-analysis document-inventory \
  --root . \
  --json-out reports/noncanonical-documents.json \
  --markdown-out reports/noncanonical-documents.md
```

1. If an old document-inventory command is observed in a caller chain, migrate that caller to the Rust command before returning to the original task.
1. Treat the report as triage, not deletion authority.
1. Edit canonical sources, not generated evidence:
   - `.agent-canon/log-archive/eval-results/*` -> edit eval definitions, workflow prompts, or generator logic.
   - `reports/*` -> regenerate or cite as run evidence.
   - `issues/closed/*` -> open/update a new issue for new scope.
1. For missing dependency headers, either add the manifest or move the file out of source docs.
1. For duplicate headings, merge, retitle, or document why both active docs remain distinct.
1. Re-run the inventory and dependency review before closeout.
