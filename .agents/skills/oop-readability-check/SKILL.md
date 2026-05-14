---
name: oop-readability-check
description: Use when the user asks to run the OOP readability checker, OOP check, readability check, produce a mechanical OOP report table, or interpret/prioritize OOP readability results; keep mechanical tool output separate from agent analysis.
---
<!--
@dependency-start
responsibility Documents the OOP readability check and analysis skill for this repository.
upstream design ../../../agents/skills/oop-readability-check.md human-readable skill canon
upstream implementation ../../../tools/oop/python/readability.py OOP readability CLI with language selection
upstream implementation ../../../tools/oop/shared/readability_core.py defines mechanical finding categories
upstream implementation ../../../tools/agent_tools/workflow_monitor.py records optional timing evidence
@dependency-end
-->

# OOP Readability Check

1. Read `agents/skills/oop-readability-check.md`.
1. Select exactly one mode from the user's request:
   - `mechanical-only`: run the tool and report status/counts/tables only
   - `analyze-existing`: analyze an existing OOP report or JSON result
   - `run-and-analyze`: run the tool, then add agent analysis
1. Treat user-provided paths as authoritative. Do not broaden scope unless the
   user asks for broader scope.
1. In tool-running modes, use the OOP readability CLI with language selection
   delegated to the tool. The default command shape is:

   ```bash
   python3 tools/oop/python/readability.py --root . --language all <paths>
   ```

1. If the user gives no path, use the repo-local active source paths and
   exclude generated or vendored surfaces (`vendor`, `reports`, `.git`, `build`,
   `.pytest_cache`, `.ruff_cache`).
1. If the user asks for a report, render the mechanical result as tables:
   command, exit status, summary metrics, dimensions, finding kinds, hotspots,
   and the first relevant finding rows.
1. Add agent analysis only in `analyze-existing` or `run-and-analyze` mode.
   Keep it under a separate `Agent Analysis` section after the mechanical
   result. Prioritize by risk and leverage, identify likely false positives,
   cite mechanical evidence, and read hotspot files only when needed.
1. When a run bundle is active, record timing as a behavior event:
   `tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths>`.
