---
name: oop-readability-analysis
description: Use when the user asks for agent analysis, interpretation, prioritization, false-positive review, or design guidance based on OOP readability checker results; consume mechanical OOP output first and keep judgment separate from the tool report.
---
<!--
@dependency-start
responsibility Documents the agent-analysis pass for OOP readability results.
upstream design ../../../agents/skills/oop-readability-analysis.md human-readable skill canon
upstream design ../../../.agents/skills/oop-readability-check/SKILL.md produces the mechanical OOP evidence this skill consumes
upstream implementation ../../../tools/oop/shared/readability_core.py defines mechanical finding categories
@dependency-end
-->

# OOP Readability Analysis

1. Read `agents/skills/oop-readability-analysis.md`.
1. Start from existing OOP readability output: Markdown report, JSON output, or
   pasted mechanical summary. Do not rerun the tool unless evidence is missing
   or stale.
1. Keep two layers separate:
   - mechanical finding: what the tool reported
   - agent analysis: why it may matter, whether it looks like a false positive,
     and what to inspect next
1. Prioritize by risk and leverage, not by raw count alone. Consider public API
   boundaries, runtime ownership, test-only surfaces, generated code, value
   objects, protocols, and adapter contracts.
1. If code reading is needed, read only the hotspot files and their nearby call
   sites. Do not expand into full workflow validation unless requested.
1. Output should lead with actionable interpretation: top risks, likely false
   positives, recommended next checks, and any user-decision points.
