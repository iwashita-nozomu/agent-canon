# html-experiment-report
<!--
@dependency-start
contract skill
responsibility Documents the HTML experiment report workflow and display contract.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design structure-planning.md reusable structure contract skill
upstream design report-writing.md reader-facing report quality criteria
upstream design html-output.md browser-readable HTML layout and publication skill
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design experiment-lifecycle.md experiment run protocol
upstream design ../../documents/semantic_index.md semantic provider comparison and candidate authority boundary
downstream implementation ../../.agents/skills/html-experiment-report/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/semantic_provider_html_report.py renders semantic provider comparison HTML reports
@dependency-end
-->

## Reader Map

- Purpose: routes experiment or Eval evidence into a browser-readable HTML
  report with a first-figure plan and bounded rendering workflow.
- Use When: the user asks for an HTML report, dashboard, browser view, or
  visual inspection artifact for experiment, benchmark, Eval, or workflow logs.
- Section path: Purpose and Use When set scope; Required Order is the mandatory
  checklist; Primary Figure Contract and Semantic Provider Report Path capture
  report-specific obligations; Closeout Tokens lists completion evidence.
- Boundary: raw artifact storage, experiment scheduling, and domain decisions
  stay with the owning skills or tools.

## Purpose

`html-experiment-report` is the skill for turning an experiment or Eval artifact
into a browser-readable HTML report. It owns the display workflow: decide the
first figure, plan the experiment from that figure, reuse existing assets, add a
report-specific renderer or experiment adapter when needed, run it, and publish
a bounded HTML artifact.

For the first figure and report shape, call `structure-planning` before writing
renderer code or running follow-up experiments. This keeps figure choice,
source mapping, metric caveats, and invalid interpretations reusable across
HTML, Markdown reports, and experiment plans.

For page layout, optional ImageGen visual assets, local server reuse, external
browser publication, and URL validation, call `html-output`. This skill owns the
experiment-specific evidence plan; `html-output` owns the browser delivery.

It does not own raw artifact storage, experiment scheduling, or domain
authority. Use `result-artifact-writeout` for raw evidence placement,
`experiment-lifecycle` for experiment protocol, and the domain tool or workflow
for the actual candidate logic.

## Use When

- A user asks for an HTML report, browser view, dashboard-like experiment view,
  or visual report artifact.
- A tool result needs visual inspection before a workflow, skill, tool, or
  document change is accepted.
- Semantic-index provider deltas, Eval outputs, benchmark results, or workflow
  logs need a reader guide plus a first figure.
- The report must separate observed facts from inferred interpretation.

## Required Order

1. Existing asset survey: inspect relevant skills, tools, workflow docs,
   previous run artifacts, and report helpers before writing new code.
1. Responsibility analysis: define what owns the raw evidence, what owns the
   renderer, what owns the domain decision, and where generated artifacts live.
1. Structure planning: use `structure-planning` to name the first figure before
   implementation and record the question it answers, required data, denominator
   and directionality for metrics, section order, and invalid interpretations.
1. HTML output planning: use `html-output` to fix the first viewport, layout
   quality gate, optional `$imagegen` asset route, existing server reuse check,
   external browser URL, and HTTP validation command.
1. Experiment plan: derive the commands, inputs, report path, success criteria,
   blocked-provider behavior, and validation gates from the figure contract.
1. Renderer implementation: reuse existing data producers and write a
   report-specific renderer or adapter only when needed to produce the HTML.
1. Execution: run the producer and renderer, storing generated JSON, SQLite,
   and HTML under an ignored run artifact path such as `reports/agents/<run-id>/`.
1. Reader report: put the primary figure first, then source packet, observations,
   interpretation, limitations, provenance, and next action.
1. Validation: run targeted tests for the renderer, docs checks for changed
   Markdown, and catalog/dependency checks for changed tool or skill surfaces.

## Primary Figure Contract

Every HTML experiment report starts with a figure contract like this:

```text
figure_name=<short title>
question=<one sentence>
required_data=<paths or fields>
metric_denominator=<what each ratio divides by>
directionality=<higher/lower/diagnostic>
invalid_interpretations=<what the figure must not be used to claim>
```

For semantic-index provider comparison, the default first figure is
`Provider Delta To Shared Candidate Logic`. It shows left and right embedding
providers feeding different retrieval and merge-candidate deltas into the same
responsibility-scoped candidate logic. The valid reading is provider divergence
or overlap. The invalid reading is that the LLM provider created labels,
ownership decisions, or merge authority.

## Semantic Provider Report Path

Use the Rust semantic-index tool as the evidence producer:

```bash
agent-canon semantic-index compare-providers \
  --db reports/semantic-index.sqlite \
  --query-file reports/search_query.txt \
  --right-provider llama-server-embedding \
  --right-model <embedding-model> \
  --report reports/agents/<run-id>/semantic_provider_compare.json
```

Then render the HTML view:

```bash
python3 tools/agent_tools/semantic_provider_html_report.py \
  --compare-json reports/agents/<run-id>/semantic_provider_compare.json \
  --output reports/agents/<run-id>/semantic_provider_compare.html
```

The HTML report is evidence for review. It is not a second policy surface and
must not replace `semantic-index` candidate generation, `eval-output`, or
responsibility-scope checks.

## Closeout Tokens

Record these in `workflow_monitoring.md`, the run bundle, or the report:

```text
html_experiment_report=complete
html_primary_figure=<figure-name>
structure_contract=<path-or-inline>
html_source_artifact=<path>
html_report_artifact=<path>
html_domain_authority=<tool-or-doc>
html_output=complete
html_server_mode=<reuse|started|not_requested|blocked>
html_invalid_interpretations_recorded=yes
```
