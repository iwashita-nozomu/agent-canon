---
name: dependency-analysis
description: Use when checking, validating, or diagnosing repository dependency manifests with the header, scan, format, and graph tools before editing, review, or closeout.
---

<!--
@dependency-start
upstream design ../../../documents/dependency-manifest-design.md defines manifest format and graph semantics
upstream design ../../../agents/canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ../../../agents/skills/dependency-analysis.md documents the human-facing skill
@dependency-end
-->

# Dependency Analysis

1. Read `documents/dependency-manifest-design.md`.
1. Choose the smallest mode that answers the task:
   - changed-file closeout gate: use `--changed`
   - explicit file review: pass file paths explicitly
   - repo migration inventory: run full scan without `--changed`
   - dependency edge change: include graph validation
1. For changed human-authored text files, run:

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

1. When dependency edges were added or changed, run:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

1. For full-repo migration inventory, run report-only scan first:

```bash
bash tools/agent_tools/scan_dependency_headers.sh
```

1. For full graph baseline, run:

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

1. Treat changed-file header / scan / format failures as fix-now blockers.
1. During migration, full graph failures may be a baseline, but do not call them pass. Record the baseline and confirm the current diff introduced no new old-format header, self reference, missing reverse edge, kind mismatch, or cycle.
1. Put command outputs and any baseline decision in `verification.txt` and `closeout_gate.md`.
