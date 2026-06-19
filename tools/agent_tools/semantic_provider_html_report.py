#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Renders semantic-index provider comparison JSON as a self-contained HTML report.
# upstream design ../../documents/semantic_index.md defines provider comparison and candidate authority boundaries
# upstream design ../../agents/skills/html-experiment-report.md defines the HTML experiment report workflow
# upstream design ../../agents/skills/report-writing.md defines reader-facing report quality criteria
# downstream implementation ../../tests/agent_tools/test_semantic_provider_html_report.py tests semantic provider HTML rendering
# downstream design ../../documents/tools/semantic_provider_html_report.md documents the tool contract
# @dependency-end
"""Render semantic-index provider comparison JSON as HTML."""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

JsonObject = dict[str, object]


@dataclass(frozen=True)
class ProviderSummary:
    """Provider provenance shown in the report."""

    side: str
    provider: str
    model: str
    dim: int
    nodes: int
    merge_candidates: int


@dataclass(frozen=True)
class DeltaSummary:
    """One overlap/delta section from compare-providers output."""

    name: str
    left_count: int
    right_count: int
    shared_count: int
    overlap_ratio: float
    shared: tuple[str, ...]
    left_only: tuple[str, ...]
    right_only: tuple[str, ...]


@dataclass(frozen=True)
class SearchDisplay:
    """Rendered search comparison fragments."""

    figure_text: str
    metric_cards: tuple[tuple[str, str], ...]
    delta_section: str
    query_chars: int


@dataclass(frozen=True)
class ReportFacts:
    """Extracted provider comparison facts for rendering."""

    left: ProviderSummary
    right: ProviderSummary
    merge: DeltaSummary
    search: SearchDisplay


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--title",
        default="Semantic Provider Comparison",
        help="HTML report title.",
    )
    return parser


def read_json_object(path: Path) -> JsonObject:
    """Read one JSON object from a file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(JsonObject, raw)


def as_object(value: object) -> JsonObject:
    """Return a JSON object or an empty object."""
    if isinstance(value, dict):
        return cast(JsonObject, value)
    return {}


def as_list(value: object) -> list[object]:
    """Return a JSON list or an empty list."""
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def as_int(value: object) -> int:
    """Return an integer for JSON number-like fields."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def as_float(value: object) -> float:
    """Return a float for JSON number-like fields."""
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def escape_text(value: object) -> str:
    """Return HTML-escaped display text."""
    return html.escape(str(value), quote=True)


def object_string_list(value: object) -> tuple[str, ...]:
    """Return display strings for JSON string/object arrays."""
    output: list[str] = []
    for item in as_list(value):
        if isinstance(item, str):
            output.append(item)
        elif isinstance(item, dict):
            data = cast(JsonObject, item)
            path = str(data.get("path", ""))
            node_kind = str(data.get("node_kind", ""))
            line_start = data.get("line_start", "")
            line_end = data.get("line_end", "")
            rank = data.get("rank", "")
            score = data.get("score", "")
            output.append(
                f"rank {rank} score {score} {path}:{node_kind}:{line_start}-{line_end}"
            )
        else:
            output.append(str(item))
    return tuple(output)


def provider_summary(report: JsonObject, side: str) -> ProviderSummary:
    """Extract provider provenance for one side."""
    raw = as_object(report.get(side, {}))
    return ProviderSummary(
        side=side,
        provider=str(raw.get("provider", "")),
        model=str(raw.get("model", "")),
        dim=as_int(raw.get("dim", 0)),
        nodes=as_int(raw.get("nodes", 0)),
        merge_candidates=as_int(raw.get("merge_candidates", 0)),
    )


def delta_summary(name: str, raw: object) -> DeltaSummary:
    """Extract overlap and left/right-only lists from one delta section."""
    data = as_object(raw)
    return DeltaSummary(
        name=name,
        left_count=as_int(data.get("left_count", 0)),
        right_count=as_int(data.get("right_count", 0)),
        shared_count=as_int(data.get("shared_count", 0)),
        overlap_ratio=as_float(data.get("overlap_ratio", 0.0)),
        shared=object_string_list(data.get("shared", [])),
        left_only=object_string_list(data.get("left_only", [])),
        right_only=object_string_list(data.get("right_only", [])),
    )


def percent(value: float) -> str:
    """Format an overlap ratio."""
    return f"{value * 100:.1f}%"


def provider_label(provider: ProviderSummary) -> str:
    """Return compact provider label."""
    model = provider.model or "unknown-model"
    name = provider.provider or "unknown-provider"
    return f"{name} / {model} / dim {provider.dim}"


def render_list(title: str, items: tuple[str, ...]) -> str:
    """Render a compact evidence list."""
    if not items:
        return (
            f"<div class=\"list-block\"><h3>{escape_text(title)}</h3>"
            '<p class="muted">none in the reported top set</p></div>'
        )
    rows = "\n".join(f"<li><code>{escape_text(item)}</code></li>" for item in items)
    return f"<div class=\"list-block\"><h3>{escape_text(title)}</h3><ol>{rows}</ol></div>"


def render_provider_table(left: ProviderSummary, right: ProviderSummary) -> str:
    """Render provider provenance."""
    rows: list[str] = []
    for item in (left, right):
        rows.append(
            "<tr>"
            f"<td>{escape_text(item.side)}</td>"
            f"<td>{escape_text(item.provider)}</td>"
            f"<td>{escape_text(item.model)}</td>"
            f"<td>{item.dim}</td>"
            f"<td>{item.nodes}</td>"
            f"<td>{item.merge_candidates}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>side</th><th>provider</th><th>model</th><th>dim</th>"
        "<th>nodes</th><th>merge candidates</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def search_metric_cards(search: DeltaSummary) -> tuple[tuple[str, str], ...]:
    """Return metric cards for a recorded search comparison."""
    return (
        ("search overlap", percent(search.overlap_ratio)),
        ("search shared", str(search.shared_count)),
        ("search left-only", str(len(search.left_only))),
        ("search right-only", str(len(search.right_only))),
    )


def render_metric_cards(
    merge: DeltaSummary,
    search_cards: tuple[tuple[str, str], ...],
) -> str:
    """Render primary metrics."""
    cards = [
        ("merge overlap", percent(merge.overlap_ratio)),
        ("merge shared", str(merge.shared_count)),
        ("merge left-only", str(len(merge.left_only))),
        ("merge right-only", str(len(merge.right_only))),
    ]
    cards.extend(search_cards)
    content = "\n".join(
        f"<div class=\"metric\"><span>{escape_text(label)}</span><strong>{escape_text(value)}</strong></div>"
        for label, value in cards
    )
    return f"<section class=\"metrics\">{content}</section>"


def render_primary_figure(
    left: ProviderSummary,
    right: ProviderSummary,
    merge: DeltaSummary,
    search_text: str,
) -> str:
    """Render the first figure for the report."""
    return f"""
<figure class="primary-figure" aria-label="Provider delta to shared candidate logic">
  <svg viewBox="0 0 980 320" role="img">
    <title>Provider Delta To Shared Candidate Logic</title>
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
        markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#4f5f6f" />
      </marker>
    </defs>
    <rect x="30" y="42" width="260" height="92" rx="8" class="provider-left" />
    <text x="52" y="76" class="box-title">left provider</text>
    <text x="52" y="103" class="box-text">{escape_text(provider_label(left))}</text>
    <rect x="690" y="42" width="260" height="92" rx="8" class="provider-right" />
    <text x="712" y="76" class="box-title">right provider</text>
    <text x="712" y="103" class="box-text">{escape_text(provider_label(right))}</text>
    <path d="M 290 88 C 390 88, 410 150, 490 150" class="flow" />
    <path d="M 690 88 C 590 88, 570 150, 490 150" class="flow" />
    <rect x="330" y="134" width="320" height="100" rx="8" class="shared" />
    <text x="365" y="170" class="box-title">shared candidate logic</text>
    <text x="365" y="198" class="box-text">responsibility bucket / candidate filters</text>
    <path d="M 490 234 L 490 282" class="flow" />
    <rect x="300" y="268" width="380" height="36" rx="8" class="output" />
    <text x="330" y="292" class="box-text">advisory report, not merge/delete authority</text>
    <text x="52" y="182" class="small">left-only merge keys: {len(merge.left_only)}</text>
    <text x="712" y="182" class="small">right-only merge keys: {len(merge.right_only)}</text>
    <text x="365" y="246" class="small">merge overlap {escape_text(percent(merge.overlap_ratio))}; {escape_text(search_text)}</text>
  </svg>
  <figcaption>
    LLM latent vectors may change retrieval and ranking deltas. This figure keeps
    the decision boundary in the existing responsibility-scoped candidate logic.
  </figcaption>
</figure>
"""


def render_delta_section(delta: DeltaSummary) -> str:
    """Render one delta section."""
    return f"""
<section>
  <h2>{escape_text(delta.name.title())}</h2>
  <p class="reader-note">Counts compare top candidate keys from both providers.
  Overlap is shared_count divided by max(left_count, right_count).</p>
  <table>
    <thead><tr><th>left count</th><th>right count</th><th>shared count</th><th>overlap</th></tr></thead>
    <tbody><tr><td>{delta.left_count}</td><td>{delta.right_count}</td><td>{delta.shared_count}</td><td>{escape_text(percent(delta.overlap_ratio))}</td></tr></tbody>
  </table>
  <div class="lists">
    {render_list("shared", delta.shared)}
    {render_list("left only", delta.left_only)}
    {render_list("right only", delta.right_only)}
  </div>
</section>
"""


def render_top_hits(report: JsonObject) -> str:
    """Render search top hit tables when present."""
    search = as_object(report.get("search", {}))
    if not search:
        return "<section><h2>Search Top Hits</h2><p class=\"muted\">search comparison was not recorded in the input JSON.</p></section>"
    left_top = object_string_list(search.get("left_top", []))
    right_top = object_string_list(search.get("right_top", []))
    return f"""
<section>
  <h2>Search Top Hits</h2>
  <div class="lists">
    {render_list("left top hits", left_top)}
    {render_list("right top hits", right_top)}
  </div>
</section>
"""


REPORT_STYLE = """
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #607080;
      --line: #c8d2dc;
      --left: #d7ecff;
      --right: #fbe4d8;
      --shared: #e4f2df;
      --output: #f2eefb;
    }
    body {
      margin: 0;
      font: 15px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #f8fafc;
    }
    main {
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 20px 48px;
    }
    header, section, figure {
      margin: 0 0 24px;
    }
    h1, h2, h3 {
      margin: 0 0 10px;
      line-height: 1.25;
    }
    h1 { font-size: 28px; }
    h2 { font-size: 20px; }
    h3 { font-size: 15px; }
    p { margin: 0 0 12px; }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid var(--line);
    }
    th, td {
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      background: #edf2f7;
      font-weight: 650;
    }
    .primary-figure svg {
      display: block;
      width: 100%;
      height: auto;
      background: white;
      border: 1px solid var(--line);
    }
    .primary-figure figcaption, .reader-note, .muted {
      color: var(--muted);
    }
    .provider-left { fill: var(--left); stroke: #5b98c8; }
    .provider-right { fill: var(--right); stroke: #ca805b; }
    .shared { fill: var(--shared); stroke: #6fa45d; }
    .output { fill: var(--output); stroke: #9386c4; }
    .flow { fill: none; stroke: #4f5f6f; stroke-width: 2.5; marker-end: url(#arrow); }
    .box-title { font-weight: 700; font-size: 18px; }
    .box-text { font-size: 14px; }
    .small { font-size: 13px; fill: var(--muted); }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }
    .metric {
      background: white;
      border: 1px solid var(--line);
      padding: 12px;
      border-radius: 8px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .metric strong {
      display: block;
      font-size: 24px;
      margin-top: 4px;
    }
    .lists {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .list-block {
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-width: 0;
    }
    ol {
      margin: 0;
      padding-left: 20px;
    }
  </style>
"""


def render_reader_guide() -> str:
    """Render the report reader guide."""
    return """
  <section>
    <h2>Reader Guide</h2>
    <p>Inspect the primary figure first. Ratios are diagnostic overlap values:
    higher means the two providers returned more of the same top keys, lower
    means the provider changed retrieval or ranking. A lower overlap does not
    grant merge, deletion, labeling, or ownership authority.</p>
    <p><code>candidate_logic_authority=shared_responsibility_bucket</code></p>
  </section>
"""


def search_display(report: JsonObject) -> SearchDisplay:
    """Return display fragments for the search section."""
    raw_search = report.get("search")
    if raw_search is None:
        return SearchDisplay(
            figure_text="search not recorded",
            metric_cards=(),
            delta_section="",
            query_chars=0,
        )
    search = delta_summary("search", raw_search)
    return SearchDisplay(
        figure_text=f"search overlap {percent(search.overlap_ratio)}",
        metric_cards=search_metric_cards(search),
        delta_section=render_delta_section(search),
        query_chars=as_int(as_object(raw_search).get("query_chars", 0)),
    )


def report_facts(report: JsonObject) -> ReportFacts:
    """Extract report facts from compare-providers JSON."""
    return ReportFacts(
        left=provider_summary(report, "left"),
        right=provider_summary(report, "right"),
        merge=delta_summary("merge candidates", report.get("merge_candidates", {})),
        search=search_display(report),
    )


def render_report_sections(
    report: JsonObject,
    facts: ReportFacts,
    source_path: Path,
    report_title: str,
) -> str:
    """Render body sections after extracted report facts."""
    return f"""
<main>
  <header>
    <h1>{report_title}</h1>
    <p class="muted">Source: <code>{escape_text(source_path)}</code></p>
  </header>
  {render_primary_figure(facts.left, facts.right, facts.merge, facts.search.figure_text)}
  {render_metric_cards(facts.merge, facts.search.metric_cards)}
  {render_reader_guide()}
  <section>
    <h2>Provider Provenance</h2>
    {render_provider_table(facts.left, facts.right)}
  </section>
  {render_delta_section(facts.merge)}
  {facts.search.delta_section}
  {render_top_hits(report)}
  <section>
    <h2>Limitations</h2>
    <p>The report renders the supplied compare-providers JSON only. It does not
    rerun indexing, validate candidate quality, or change semantic-index
    thresholds. Query text is not embedded in this report; query length was
    {facts.search.query_chars} characters when the input recorded it.</p>
  </section>
</main>
"""


def render_html(report: JsonObject, title: str, source_path: Path) -> str:
    """Render a complete self-contained HTML document."""
    facts = report_facts(report)
    report_title = escape_text(title)
    sections = render_report_sections(
        report,
        facts,
        source_path,
        report_title,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{report_title}</title>
  {REPORT_STYLE}
</head>
<body>
{sections}
</body>
</html>
"""


def main() -> int:
    """Run the renderer."""
    args = build_parser().parse_args()
    report = read_json_object(args.compare_json)
    html_text = render_html(report, args.title, args.compare_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(f"SEMANTIC_PROVIDER_HTML_REPORT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
