---
name: document-canon-cleanup
description: Use when organizing repository documents, finding non-canonical docs, separating source canon from runtime mirrors, generated reports, eval results, closed issues, duplicate headings, or stale document paths.
---
<!--
@dependency-start
responsibility Documents Document Canon Cleanup for this repository.
upstream design ../../../agents/skills/document-canon-cleanup.md human-facing skill canon
upstream implementation ../../../tools/agent_tools/noncanonical_document_inventory.py finds cleanup candidates
@dependency-end
-->


# Document Canon Cleanup

1. Read `agents/skills/document-canon-cleanup.md`.
1. Run:

```bash
python3 tools/agent_tools/noncanonical_document_inventory.py \
  --root . \
  --json-out reports/noncanonical-documents.json \
  --markdown-out reports/noncanonical-documents.md
```

1. Treat the report as triage, not deletion authority.
1. Edit canonical sources, not mirrors or generated evidence:
   - `.claude/skills/*/SKILL.md` -> edit `.agents/skills/*/SKILL.md`, then run `mirror_skill_shims.py`.
   - `.agent-canon/log-archive/eval-results/*` -> edit eval definitions, workflow prompts, or generator logic.
   - `reports/*` -> regenerate or cite as run evidence.
   - `issues/closed/*` -> open/update a new issue for new scope.
1. For missing dependency headers, either add the manifest or move the file out of source docs.
1. For duplicate headings, merge, retitle, or document why both active docs remain distinct.
1. Re-run the inventory and dependency review before closeout.
