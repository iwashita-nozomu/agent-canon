# oop-readability-check
<!--
@dependency-start
responsibility Documents oop-readability-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream implementation ../../tools/oop/python/readability.py OOP readability CLI
upstream implementation ../../tools/agent_tools/workflow_monitor.py optional timing recorder
downstream design ../../.agents/skills/oop-readability-check/SKILL.md Codex/Copilot discovery shim
downstream design ../../.claude/skills/oop-readability-check/SKILL.md Claude discovery mirror
@dependency-end
-->

## Purpose

Run the OOP readability checker as a narrow mechanical check.
This skill exists so a user can request the tool without triggering a broader
workflow, report-writing pass, or agent interpretation pass.

## Use When

- The user says `$oop-readability-check`.
- The user asks to run the OOP tool, OOP check, readability check, or mechanical
  OOP report.
- The user wants tool output, tables, status, counts, or hotspot rows.

## Default Command

```bash
python3 tools/oop/python/readability.py \
  --root . \
  --language all \
  --format json \
  --exclude vendor \
  --exclude reports \
  --exclude .git \
  --exclude build \
  --exclude .pytest_cache \
  --exclude .ruff_cache \
  <paths>
```

Use `--language all` unless the user explicitly asks for Python-only or
C++-only. The tool should decide which files are relevant by suffix.

## Scope Rules

- If the user provides paths, use exactly those paths.
- If the user says "Pythonそのまま", use `python` as the path. Do not silently
  remove tests or `_test` files.
- If no paths are provided, use active repo source paths and the excludes above.
- Do not add `vendor/agent-canon` unless the user asks for AgentCanon.
- Do not run Markdown and JSON variants unless both are needed for the requested
  output.

## Mechanical Report Tables

When a report is requested, render tables only from one tool result:

- command and exit status
- summary metrics
- severity counts
- dimension counts
- finding kind counts
- hotspot files
- first relevant finding rows

Do not add prioritization, false-positive calls, or design recommendations.
Those belong to `$oop-readability-analysis`.

## Timing Token

When a run bundle is active, append a workflow monitoring behavior event:

```text
tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths> output_path=<path-or-none>
```

If there is no run bundle, include elapsed time in the user-facing summary only
when it is useful.

## Boundary

- This skill can say that the tool reported `status=fail`.
- This skill must not decide whether a finding is a true design problem.
- This skill must not start a refactor or broad validation pass.
- This skill must not clean unrelated hook logs except to avoid presenting them
  as product changes.
