# oop-readability-analysis
<!--
@dependency-start
responsibility Documents oop-readability-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design oop-readability-check.md mechanical OOP check source
upstream implementation ../../tools/oop/shared/readability_core.py defines mechanical OOP findings
downstream design ../../.agents/skills/oop-readability-analysis/SKILL.md Codex/Copilot discovery shim
downstream design ../../.claude/skills/oop-readability-analysis/SKILL.md Claude discovery mirror
@dependency-end
-->

## Purpose

Interpret OOP readability checker output without mixing the interpretation into
the mechanical tool report.
This skill turns raw findings into review judgment, likely false-positive notes,
and next investigation steps.

## Use When

- The user says `$oop-readability-analysis`.
- The user asks "この OOP 結果を解釈して", "優先順位をつけて", "false positive を見て",
  or asks for agent judgment about an OOP readability report.
- A mechanical report from `$oop-readability-check` already exists and needs
  design-level interpretation.

## Inputs

Prefer one of these inputs:

- OOP Markdown report.
- OOP JSON output.
- Pasted mechanical summary with hotspot rows.
- A report path under `reports/agents/`.

If no usable mechanical evidence exists, ask to run `$oop-readability-check` or
run it only when the user has already authorized tool execution.

## Analysis Rules

- Keep "tool reported" separate from "agent judgment".
- Prioritize findings by design risk and user relevance, not count alone.
- Treat test-only files, generated files, value objects, protocol contracts, and
  adapter functions as likely false-positive candidates until code reading says
  otherwise.
- For production code, focus first on public API boundaries, ownership/lifetime,
  broad optional/null-driven routing, and large effectful functions.
- Read hotspot files and nearby call sites only as needed.
- Do not broaden into a refactor plan unless the user asks for fixes.

## Output Shape

Use a concise findings-first shape:

- top risks
- likely false positives
- recommended next checks
- user-decision points
- mechanical evidence cited by path, line, symbol, kind, and count

Do not restate every raw finding when the mechanical report already contains
tables.
