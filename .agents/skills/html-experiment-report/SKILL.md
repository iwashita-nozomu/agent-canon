---
name: html-experiment-report
description: Use when producing a browser-readable HTML experiment or Eval report; first decide the primary figure, then plan and run an evidence-backed report renderer while keeping domain authority in the original tool.
---
<!--
@dependency-start
contract skill
responsibility Documents HTML Experiment Report runtime skill for this repository.
upstream design ../../../agents/skills/html-experiment-report.md documents the canonical HTML experiment report workflow
upstream design ../../../agents/skills/structure-planning.md defines reusable structure contracts
upstream design ../../../agents/skills/report-writing.md defines reader-facing report quality gates
upstream design ../../../agents/skills/html-output.md defines HTML layout, ImageGen, and browser publication
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw artifact placement
upstream design ../../../documents/semantic_index.md defines semantic provider comparison authority boundaries
downstream implementation ../../../tools/agent_tools/semantic_provider_html_report.py renders semantic provider comparison HTML reports
@dependency-end
-->

# HTML Experiment Report

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill html-experiment-report --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/html-experiment-report.md`.
1. Use `$structure-planning` before renderer or experiment implementation to fix the first figure, source-to-structure map, metric contract, section order, and invalid interpretations.
1. Use `$html-output` for polished HTML layout, optional `$imagegen` assets, existing preview-server reuse, `python3 -m http.server --bind 0.0.0.0` publication, `curl -fsS` validation, and local/external browser URLs.
1. Survey existing assets first: relevant skills, tool catalog entries, workflow
   docs, report helpers, previous run artifacts, and existing experiment
   scripts.
1. Write a responsibility analysis before implementation: raw evidence owner,
   renderer owner, domain decision owner, generated artifact path, and the
   invalid authority drift to avoid.
1. Name the first figure through the structure contract before running the
   experiment. Record its question, required data, metric denominator,
   directionality, and invalid interpretations.
1. Derive the experiment plan from that figure: evidence-producing command,
   renderer command, HTML output path, blocked-provider behavior, and validation
   gates.
1. Reuse existing producers and helpers. Add a report-specific renderer or
   adapter only when the HTML artifact needs one.
1. Keep generated SQLite, JSON, and HTML artifacts under ignored run paths such
   as `reports/agents/<run-id>/`; do not make generated HTML a policy truth.
1. Put the primary figure first in the HTML, followed by source packet,
   observations, interpretation, limitations, provenance, and next action.
1. For semantic-index provider comparison, use the figure
   `Provider Delta To Shared Candidate Logic` and state that LLM latent vectors
   may change retrieval/ranking deltas but do not create labels, ownership, or
   merge authority.
1. Validate with targeted renderer tests, docs checks for changed Markdown, and
   catalog/dependency checks for changed tool or skill wiring.
1. Record closeout tokens:
   `html_experiment_report=complete`,
   `html_primary_figure=<figure-name>`,
   `structure_contract=<path-or-inline>`,
   `html_source_artifact=<path>`,
   `html_report_artifact=<path>`,
   `html_domain_authority=<tool-or-doc>`, and
   `html_output=complete`,
   `html_server_mode=<reuse|started|not_requested|blocked>`, and
   `html_invalid_interpretations_recorded=yes`.
