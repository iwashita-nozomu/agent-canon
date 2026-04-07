---
name: artifact-placement
description: Use when deciding where task-related documents, run notes, reports, or extension writeups should live so run-local artifacts do not leak into repo-wide canon.
---

# Artifact Placement

1. Read `agents/canonical/ARTIFACT_PLACEMENT.md`.
1. Keep run-local material in `reports/agents/<run-id>/` and reuse the standard artifact files before inventing new ones.
1. Put reusable cross-agent rules in `agents/`.
1. Put general workflow or development rules in `documents/`.
1. Put cross-run knowledge and summaries in `notes/`.
1. If a role is artifact-only, do not create ad hoc report files outside its allowed artifact set.
