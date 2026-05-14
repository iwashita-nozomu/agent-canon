---
name: oop-readability-check
description: Use when the user asks to run the OOP readability checker, OOP check, readability check, or produce a mechanical OOP report table; execute the tool on the requested paths, let the tool select language coverage, and avoid agent interpretation unless a separate analysis skill is requested.
---
<!--
@dependency-start
responsibility Documents the mechanical OOP readability check skill for this repository.
upstream design ../../../agents/skills/oop-readability-check.md human-readable skill canon
upstream implementation ../../../tools/oop/python/readability.py OOP readability CLI with language selection
upstream implementation ../../../tools/agent_tools/workflow_monitor.py records optional timing evidence
@dependency-end
-->

# OOP Readability Check

1. Read `agents/skills/oop-readability-check.md`.
1. Treat the user-provided path list as authoritative. Do not broaden scope
   unless the user asks for broader scope.
1. Use the OOP readability CLI with language selection delegated to the tool.
   The default command shape is:

   ```bash
   python3 tools/oop/python/readability.py --root . --language all <paths>
   ```

1. If the user gives no path, use the repo-local active source paths and
   exclude generated or vendored surfaces (`vendor`, `reports`, `.git`, `build`,
   `.pytest_cache`, `.ruff_cache`).
1. If the user asks for a report, render the mechanical result as tables:
   command, exit status, summary metrics, dimensions, finding kinds, hotspots,
   and the first relevant finding rows.
1. Do not add agent judgment, priority, or false-positive analysis. Use
   `$oop-readability-analysis` for that.
1. When a run bundle is active, record timing as a behavior event:
   `tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths>`.
