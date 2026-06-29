# html-output
<!--
@dependency-start
contract skill
responsibility Documents browser-readable HTML output, preview, and publication workflow.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design structure-planning.md reusable structure contract skill
upstream design report-writing.md reader-facing report quality skill and Markdown default
downstream design html-experiment-report.md experiment-specific HTML report workflow
downstream implementation ../../.agents/skills/html-output/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: produce browser-readable HTML artifacts with layout, asset,
  preview-server, and publication evidence.
- Section path: Purpose and Use When decide whether HTML is in scope; Required
  Order defines the build sequence; Browser Server Commands, Layout Quality
  Gate, and Closeout Tokens define preview and validation.
- Use when: the user explicitly asks for HTML, a browser view, dashboard,
  external URL, local preview server, or polished HTML report artifact.
- Boundary: reports default to Markdown unless HTML is explicit; claims, raw
  evidence, experiment execution, and domain decisions stay with their owner
  skills.

## Purpose

`html-output` is the skill for producing polished browser-readable HTML
artifacts and making them available to a local or external browser. It owns the
rendered page contract, layout quality gate, optional ImageGen asset route, and
preview server commands.

It does not own report claims, raw evidence, experiment execution, or domain
decisions. Use `report-writing` for report content, `structure-planning` for
nontrivial page structure, `html-experiment-report` for experiment or Eval
HTML reports, and `result-artifact-writeout` for raw machine artifacts.

The default report output is Markdown. Reports default to Markdown unless the
user explicitly asks for HTML, a browser page, dashboard, web view, or external browser publication.

## Use When

- A user explicitly asks for HTML output, an HTML report, browser view,
  dashboard-like page, external browser URL, or local preview server.
- A generated report needs a polished layout with figures, tables, cards, or a
  first-viewport summary.
- A report or review artifact needs optional generated raster visuals through
  `$imagegen`.
- An existing HTML artifact must be served to a browser without starting a
  duplicate server.

## Required Order

1. Confirm HTML is explicit. If the user asks for a report without naming HTML,
   use Markdown through `report-writing` instead.
1. Fix the source packet: title, audience, source artifacts, observed facts,
   inferred claims, limitations, provenance, and output path.
1. Use `structure-planning` before writing page code when the page has a
   nontrivial first viewport, figure/table order, source-to-section map, or
   invalid interpretation boundary.
1. Survey existing assets, renderers, CSS, plots, screenshots, and previous
   reports before adding a new renderer.
1. Decide the visual asset route. Prefer existing repo or run artifacts. Use
   `$imagegen` only when a generated bitmap materially improves comprehension
   and no existing asset is suitable.
1. Build a self-contained HTML/CSS artifact unless the surrounding app already
   has a build system. Keep stable dimensions for figures, tables, cards, and
   media so labels, hover states, and dynamic text do not resize the layout.
1. Put the first-viewport answer first: title, short reader guide, primary
   figure/table/card, key caveat, and source packet link or summary.
1. Keep sections in reader order, not raw tool-output order. Separate observed
   facts, interpretation, limitations, provenance, and next action.
1. Validate the file exists, opens over HTTP, references only existing assets,
   has no overlapping text at expected viewport sizes, and keeps generated
   reports out of policy truth.
1. Publish with the server commands below. Reuse an existing server on the
   chosen port when it is already serving the requested file.

## Browser Server Commands

Set these variables first:

```bash
HTML_ROOT=reports/agents/<run-id>
HTML_FILE=semantic_provider_compare.html
PORT=${PORT:-8765}
```

Check whether a compatible server is already available:

```bash
if command -v rg >/dev/null 2>&1; then
  ss -ltnp 2>/dev/null | rg ":${PORT}\\b" || true
else
  ss -ltnp 2>/dev/null | grep -E ":${PORT}([[:space:]]|$)" || true
fi
curl -fsS "http://127.0.0.1:${PORT}/${HTML_FILE}" >/dev/null \
  && echo "HTML_SERVER=reuse"
```

Start a server only when the `curl` check fails:

```bash
LOG=/tmp/agentcanon-html-${PORT}.log
setsid bash -lc "cd '$HTML_ROOT' && exec python3 -m http.server '$PORT' --bind 0.0.0.0" \
  >"$LOG" 2>&1 < /dev/null &
echo $! >/tmp/agentcanon-html-${PORT}.pid
sleep 1
curl -fsS "http://127.0.0.1:${PORT}/${HTML_FILE}" >/dev/null
hostname -I | awk '{print $1}'
```

Report both URLs when the server check passes:

```text
local_url=http://127.0.0.1:<port>/<file>
external_url=http://<hostname-I-first-ip>:<port>/<file>
```

If `ss`, `rg`, or `curl` is unavailable, record the missing tool and use the
closest available equivalent such as `grep -E` for the port filter. Do not claim
external-browser availability without an HTTP check against `127.0.0.1` and a
concrete host IP from `hostname -I`.

## Layout Quality Gate

- The first viewport answers what the reader should inspect first.
- Text fits within containers on desktop and mobile widths.
- Figures, tables, cards, and media have stable responsive dimensions.
- Primary visuals reveal the actual result, product, state, or comparison.
- Generated images are cited as generated assets and do not replace evidence.
- Observations, interpretations, limitations, and provenance are visually
  distinct.
- The page can be served from its artifact directory without a repo build step,
  unless it intentionally belongs to an existing web app.

## Closeout Tokens

Record these in `workflow_monitoring.md`, a run bundle, or the HTML report:

```text
html_output=complete
html_output_file=<path>
html_source_packet=<path-or-inline>
html_layout_check=<pass|fail>
html_server_mode=<reuse|started|not_requested|blocked>
html_server_local_url=<url|not_requested|blocked>
html_server_external_url=<url|not_requested|blocked>
html_imagegen=<used|not_required>
html_policy_truth=<no>
```
