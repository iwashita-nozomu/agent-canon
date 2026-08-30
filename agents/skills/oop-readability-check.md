# oop-readability-check
<!--
@dependency-start
contract skill
responsibility Documents oop-readability-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream implementation ../../tools/validation/code/oop/python/readability.py OOP readability CLI
upstream implementation ../../tools/validation/code/oop/shared/readability_core.py defines mechanical finding categories
upstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py optional timing recorder
downstream design ../../.codex/personal/skills/oop-readability-check/SKILL.md Codex discovery shim
@dependency-end
-->

## Reader Map

- Purpose: run the OOP readability checker and keep mechanical results separate
  from optional agent interpretation.
- Section path: Purpose and Use When identify triggers; Modes, Default Command,
  Scope Rules, and Mechanical Result define execution; Agent Analysis, Timing
  Token, and Boundary describe interpretation and limits.
- Use when: a user asks for OOP, SOLID, readability, class responsibility,
  inheritance, protocol, API-width, or dependency-inversion evidence.
- Boundary: language-specific review skills consume this evidence for changed
  code; this skill owns the mechanical report and optional separated analysis.

## Purpose

Run the OOP readability checker and, when requested, interpret its result.
This skill exists so a user can request OOP checking through one trigger while
still keeping mechanical tool output separate from agent judgment.

## Use When

- The user says `$oop-readability-check`.
- The user asks to run the OOP tool, OOP check, readability check, or mechanical
  OOP report.
- The user asks about SOLID, Single responsibility, Open/closed, Liskov
  substitution, Interface segregation, Dependency inversion, class
  responsibility, public API width, `Protocol`, inheritance, or dependency
  inversion signals.
- The user wants tool output, tables, status, counts, or hotspot rows.
- The user asks to interpret, prioritize, or review false positives in OOP
  readability output.

SOLID route owner: this skill owns SOLID check prompts and mechanical SOLID
signal reports. Language-specific review skills consume the resulting evidence
when their changed diff already owns that language surface.

## Modes

- `mechanical-only`: run the tool and return command, status, metrics, counts,
  hotspots, and relevant finding rows.
- `analyze-existing`: start from an existing Markdown report, JSON output, or
  pasted summary. Do not rerun the tool unless evidence is missing or stale.
- `run-and-analyze`: run the tool, then add a clearly separated interpretation
  pass.

## Default Command

```bash
python3 tools/validation/code/oop/python/readability.py \
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

## Mechanical Result

When a report is requested or any tool-running mode runs the tool, create a
Markdown report artifact by default. Chat-only tables are insufficient unless
the user explicitly says no file / chat only.
Use `result-artifact-writeout` when the OOP result must be retained beyond the
chat turn: the checker output is the raw result, the Markdown table is the
summary artifact, and both point to the same run.

Default artifact path:

```text
reports/agents/<run-id-or-oop-readability-YYYYMMDD-HHMMSS>/oop_readability_<scope>.md
```

Use one tool result as the source of truth. Prefer a single Markdown run when a
report file is needed:

```bash
python3 tools/validation/code/oop/python/readability.py \
  --root . \
  --language all \
  --format markdown \
  --max-report-findings 80 \
  --exclude vendor \
  --exclude reports \
  --exclude .git \
  --exclude build \
  --exclude .pytest_cache \
  --exclude .ruff_cache \
  <paths> > <artifact-path>
```

If JSON is needed for post-processing, save it as a sibling implementation
artifact and derive the Markdown tables from that same JSON result. Do not rerun
with different flags and merge counts from multiple outputs.

The Markdown report must include mechanical tables for:

- command and exit status
- summary metrics
- severity counts
- SOLID principle signal counts
- dimension counts
- finding kind counts
- hotspot files
- first relevant finding rows

SOLID principle signal counts are mechanical projections from finding kind to
review heading. The source mapping lives in
`tools/validation/code/oop/shared/readability_core.py`; keep the skill as routing and report
usage guidance.
Reports should preserve all five headings when present: Single responsibility,
Open/closed, Liskov substitution, Interface segregation, and Dependency inversion.

The user-facing response must include the artifact path, status, and headline
counts. It may include a short table excerpt, but the durable report is the
Markdown artifact.

Do not mix prioritization, false-positive calls, or design recommendations into
the mechanical result.

## Agent Analysis

Only include this section in `analyze-existing` or `run-and-analyze` mode.

- Keep "tool reported" separate from "agent judgment".
- Prioritize by design risk and user relevance, not count alone.
- Treat `typed_boundary_evidence` as mechanical evidence owned by the checker.
  Use `status`, `status_reason`, boundary counts, and evidence refs together;
  never turn a scalar heuristic into the design judgment.
- Treat public-surface, parameter-count, and complexity findings as boundary
  review signals, not automatic split/extract or private-helper instructions.
  Recommend a boundary change only after caller contracts, ownership, or
  surrounding source shape show a stable split point.
- Treat test-only files, generated files, value objects, protocol contracts,
  and adapter functions as likely false-positive candidates until code reading
  says otherwise.
- For production code, focus first on public API boundaries,
  ownership/lifetime, broad optional/null-driven routing, and large effectful
  functions.
- Use SOLID principle signal groups as the first review grouping, then cite the
  underlying OOP dimension and finding kind.
- Read hotspot files and nearby call sites only as needed.
- Do not broaden into a refactor plan unless the user asks for fixes.

Use this output shape:

- top risks
- likely false positives
- recommended next checks
- user-decision points
- mechanical evidence cited by path, line, symbol, kind, and count

## Timing Token

When a run bundle is active, append a workflow monitoring behavior event:

```text
tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths> output_path=<path-or-none>
```

If there is no run bundle, include elapsed time in the user-facing summary only
when it is useful.

## Boundary

- This skill can say that the tool reported `status=fail`.
- This skill can decide whether a finding is likely important only inside a
  separate `Agent Analysis` section.
- This skill must not start a refactor or broad validation pass.
- This skill must not clean unrelated hook logs except to avoid presenting them
  as product changes.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

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
   Treat `typed_boundary_evidence` as mechanical evidence owned by the checker.
   Use `status`, `status_reason`, boundary counts, and evidence refs together;
   never turn a scalar heuristic into the design judgment.
   Treat public-surface, parameter-count, and complexity findings as boundary
   review signals, not automatic split/extract or private-helper instructions.
   Only recommend a boundary change after reading the caller contract, ownership,
   or surrounding source shape that makes the split stable.
1. When a run bundle is active, record timing as a behavior event:
   `tool_call=oop-readability-check duration_ms=<n> status=<pass|fail> scope=<paths>`.
