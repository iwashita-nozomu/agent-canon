---
name: html-output
description: Use when the user explicitly asks for HTML output, a browser-readable page, dashboard/report HTML, external browser publication, or local preview server; defaults reports to Markdown unless HTML is explicit.
---
<!--
@dependency-start
contract skill
responsibility Documents HTML Output runtime skill for this repository.
upstream design ../../../agents/skills/html-output.md documents the canonical HTML output workflow
upstream design ../../../agents/skills/structure-planning.md defines reusable page structure contracts
upstream design ../../../agents/skills/report-writing.md defines report content and Markdown default
upstream design ../../../agents/skills/html-experiment-report.md defines experiment-specific HTML report routing
@dependency-end
-->

# HTML Output

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill html-output --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/html-output.md`.
1. Confirm HTML is explicit. If the user asks for a report without saying HTML,
   browser view, dashboard, web page, or external browser publication, default to Markdown through `$report-writing` instead.
1. Fix the source packet: title, audience, source artifacts, observed facts,
   inferred claims, limitations, provenance, and output path.
1. Use `$structure-planning` before writing page code when the first viewport,
   figure/table order, source-to-section map, or invalid interpretation
   boundary is nontrivial.
1. Survey existing assets, renderers, CSS, plots, screenshots, and prior reports
   before adding a new renderer.
1. Prefer existing visuals. Use `$imagegen` only when a generated bitmap
   materially improves comprehension and no existing asset is suitable; store
   generated assets beside the HTML artifact and cite them as generated assets.
1. Build a polished self-contained HTML/CSS artifact unless an existing app
   build system owns the page. Use stable dimensions, responsive constraints,
   readable tables/figures/cards, and no overlapping text.
1. Put the first-viewport answer first: title, reader guide, primary visual or
   table, key caveat, and source packet link or summary.
1. Validate that the file exists, asset references resolve, generated reports do
   not become policy truth, and layout quality passes at expected desktop and
   mobile widths.
1. Publish or reuse a preview server with these commands, replacing variables:
   `HTML_ROOT=reports/agents/<run-id>`, `HTML_FILE=<file>.html`,
   `PORT=${PORT:-8765}`.
1. Check existing server first:
   `if command -v rg >/dev/null 2>&1; then ss -ltnp 2>/dev/null | rg ":${PORT}\\b" || true; else ss -ltnp 2>/dev/null | grep -E ":${PORT}([[:space:]]|$)" || true; fi` and
   `curl -fsS "http://127.0.0.1:${PORT}/${HTML_FILE}" >/dev/null && echo "HTML_SERVER=reuse"`.
1. If the `curl` check fails, start the server:
   `LOG=/tmp/agentcanon-html-${PORT}.log; setsid bash -lc "cd '$HTML_ROOT' && exec python3 -m http.server '$PORT' --bind 0.0.0.0" >"$LOG" 2>&1 < /dev/null & echo $! >/tmp/agentcanon-html-${PORT}.pid; sleep 1; curl -fsS "http://127.0.0.1:${PORT}/${HTML_FILE}" >/dev/null; hostname -I | awk '{print $1}'`.
1. Report both `http://127.0.0.1:<port>/<file>` and
   `http://<hostname-I-first-ip>:<port>/<file>` only after the HTTP check
   passes.
1. Record closeout tokens:
   `html_output=complete`,
   `html_output_file=<path>`,
   `html_source_packet=<path-or-inline>`,
   `html_layout_check=<pass|fail>`,
   `html_server_mode=<reuse|started|not_requested|blocked>`,
   `html_server_local_url=<url|not_requested|blocked>`,
   `html_server_external_url=<url|not_requested|blocked>`,
   `html_imagegen=<used|not_required>`, and
   `html_policy_truth=no`.
