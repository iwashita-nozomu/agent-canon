---
name: oop-readability-check
description: Use when the user asks to run the OOP readability checker, SOLID check, OOP check, readability check, produce a mechanical OOP report table, or interpret/prioritize OOP readability results; keep mechanical tool output separate from agent analysis.
---
<!--
@dependency-start
contract skill
responsibility Documents the OOP readability check and analysis skill for this repository.
upstream design ../../../agents/skills/oop-readability-check.md human-readable skill canon
upstream implementation ../../../tools/oop/python/readability.py OOP readability CLI with language selection
upstream implementation ../../../tools/oop/shared/readability_core.py defines mechanical finding categories
upstream implementation ../../../tools/agent_tools/workflow_monitor.py records optional timing evidence
@dependency-end
-->

# OOP Readability Check

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill oop-readability-check --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/oop-readability-check.md`.
1. Select exactly one mode from the user's request:
   - `mechanical-only`: run the tool and report status/counts/tables only
   - `analyze-existing`: analyze an existing OOP report or JSON result
   - `run-and-analyze`: run the tool, then add agent analysis
1. Treat user-provided paths as authoritative. Do not broaden scope unless the
   user asks for broader scope.
1. Treat SOLID, Single responsibility, Open/closed, Liskov substitution,
   Interface segregation, Dependency inversion, class responsibility, public API
   width, `Protocol`, inheritance, and dependency inversion prompts as OOP
   readability scope.
1. Treat this skill as the SOLID route owner for SOLID check prompts and
   mechanical SOLID signal reports; language-specific review skills consume the
   report only when their changed diff already owns that language surface. Keep
   SOLID labels as mechanical projections of the checker categories.
1. In tool-running modes, use the OOP readability CLI with language selection
   delegated to the tool. The default command shape is:

   ```bash
   python3 tools/oop/python/readability.py --root . --language all <paths>
   ```

1. If the user gives no path, use the repo-local active source paths and
   exclude generated or vendored surfaces (`vendor`, `reports`, `.git`, `build`,
   `.pytest_cache`, `.ruff_cache`).
1. If the user asks for a report, render the mechanical result as tables:
   command, exit status, summary metrics, SOLID principle signals, dimensions,
   finding kinds, hotspots, and the first relevant finding rows.
1. In any tool-running mode, create a Markdown report artifact by default at
   `reports/agents/<run-id-or-oop-readability-YYYYMMDD-HHMMSS>/oop_readability_<scope>.md`.
   Chat-only tables do not satisfy this skill unless the user explicitly says
   no file / chat only. Use `--format markdown --max-report-findings 80` for the
   artifact, or save JSON as a sibling file and derive the Markdown tables from
   that same JSON result. Include the artifact path in the final response.
1. Use `$result-artifact-writeout` when the result must persist beyond chat; save the checker output as the raw artifact and derive Markdown tables from the same source result.
1. Add agent analysis only in `analyze-existing` or `run-and-analyze` mode.
   Keep it under a separate `Agent Analysis` section after the mechanical
   result. Prioritize by risk and leverage, identify likely false positives,
   group by SOLID principle signals, cite mechanical evidence, and read hotspot
   files only when needed.
   Treat `score` as a diagnostic index. Use `status`, `status_reason`,
   `gate_signal_findings`, `review_signal_findings`, and `score_status` together
   instead of turning the numeric score into the design judgment.
   Treat size, public-surface, parameter-count, and complexity findings as
   boundary review signals, not automatic split/extract instructions. Only
   recommend a boundary change after reading the caller contract, ownership, or
   surrounding source shape that makes the split stable.
1. When a run bundle is active, record timing as a behavior event:
   `tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths>`.
