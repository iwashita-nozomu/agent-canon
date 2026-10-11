#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Projects semantic-index provider comparison JSON through Quarto as static HTML and a local SVG asset.
# upstream design ../../../../documents/tools/semantic_index.md defines provider comparison and candidate authority boundaries
# upstream design ../../../../agents/skills/html-output.md owns HTML artifact generation and validation
# upstream environment ../../../../bootstrap/container/image/dependencies.toml supplies Quarto and the offline link checker
# upstream design ../../../../agents/skills/report-writing.md defines reader-facing report quality criteria
# downstream implementation ../../../../tests/agent_tools/test_semantic_provider_html_report.py tests semantic provider HTML rendering
# downstream design ../../../../documents/tools/semantic_provider_html_report.md documents the tool contract
# @dependency-end
"""Render semantic-index provider comparison JSON through Quarto."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

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
    """Search comparison facts used by the Quarto document source."""

    figure_text: str
    metric_cards: tuple[tuple[str, str], ...]
    delta: DeltaSummary | None
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
    parser.add_argument(
        "--embed-resources",
        action="store_true",
        help="Ask Quarto to embed local HTML resources in the output.",
    )
    return parser


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


def markdown_text(value: object) -> str:
    """Keep one data value literal in Quarto using a Markdown code span."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    longest_backtick_run = 0
    current_backtick_run = 0
    for item in text:
        if item == "`":
            current_backtick_run += 1
            longest_backtick_run = max(longest_backtick_run, current_backtick_run)
        else:
            current_backtick_run = 0
    delimiter = "`" * (longest_backtick_run + 1)
    padding = " " if text.startswith(" ") or text.endswith(" ") else ""
    return f"{delimiter}{padding}{text}{padding}{delimiter}"


def markdown_list(title: str, items: tuple[str, ...]) -> str:
    """Project one evidence list as Markdown for Quarto to render."""
    lines = [f"### {title}"]
    if items:
        lines.extend(f"- {markdown_text(item)}" for item in items)
    else:
        lines.append("- none in the reported top set")
    return "\n".join(lines)


def search_metric_cards(search: DeltaSummary) -> tuple[tuple[str, str], ...]:
    """Return metric cards for a recorded search comparison."""
    return (
        ("search overlap", percent(search.overlap_ratio)),
        ("search shared", str(search.shared_count)),
        ("search left-only", str(len(search.left_only))),
        ("search right-only", str(len(search.right_only))),
    )


def metric_table(
    merge: DeltaSummary,
    search_cards: tuple[tuple[str, str], ...],
) -> str:
    """Return merge and search metrics as source Markdown."""
    cards = [
        ("merge overlap", percent(merge.overlap_ratio)),
        ("merge shared", str(merge.shared_count)),
        ("merge left-only", str(len(merge.left_only))),
        ("merge right-only", str(len(merge.right_only))),
        *search_cards,
    ]
    rows = ["| Metric | Value |", "| --- | --- |"]
    rows.extend(f"| {label} | {markdown_text(value)} |" for label, value in cards)
    return "\n".join(rows)


def render_primary_figure(
    left: ProviderSummary,
    right: ProviderSummary,
    merge: DeltaSummary,
    search_text: str,
) -> str:
    """Render only the domain-specific SVG figure used by the report."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 320" role="img" aria-labelledby="figure-title figure-description">
  <title id="figure-title">Provider Delta To Shared Candidate Logic</title>
  <desc id="figure-description">Provider retrieval and ranking deltas remain advisory; shared responsibility-scoped candidate logic retains merge and deletion authority.</desc>
  <style>
    .provider-left {{ fill: #d7ecff; stroke: #5b98c8; }}
    .provider-right {{ fill: #fbe4d8; stroke: #ca805b; }}
    .shared {{ fill: #e4f2df; stroke: #6fa45d; }}
    .output {{ fill: #f2eefb; stroke: #9386c4; }}
    .flow {{ fill: none; stroke: #4f5f6f; stroke-width: 2.5; marker-end: url(#arrow); }}
    .box-title {{ font: 700 18px sans-serif; }}
    .box-text {{ font: 14px sans-serif; }}
    .small {{ font: 13px sans-serif; fill: #607080; }}
  </style>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
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
'''


def delta_markdown(delta: DeltaSummary) -> str:
    """Return one candidate-delta section as Markdown source."""
    rows = [
        f"## {delta.name.title()}",
        "",
        "Counts compare top candidate keys from both providers. Overlap is "
        "shared_count divided by max(left_count, right_count).",
        "",
        "| Left count | Right count | Shared count | Overlap |",
        "| ---: | ---: | ---: | ---: |",
        f"| {delta.left_count} | {delta.right_count} | {delta.shared_count} | {percent(delta.overlap_ratio)} |",
        "",
        markdown_list("Shared", delta.shared),
        "",
        markdown_list("Left only", delta.left_only),
        "",
        markdown_list("Right only", delta.right_only),
    ]
    return "\n".join(rows)


def render_markdown_document(
    report: JsonObject,
    facts: ReportFacts,
    source_path: Path,
    figure_name: str,
) -> str:
    """Build Quarto Markdown from semantic comparison facts, not HTML markup."""
    search = as_object(report.get("search", {}))
    provider_sections = []
    for provider in (facts.left, facts.right):
        provider_sections.append(
            f"### {provider.side.title()} provider\n\n"
            f"- Provider: {markdown_text(provider.provider)}\n"
            f"- Model: {markdown_text(provider.model)}\n"
            f"- Dimension: {provider.dim}\n"
            f"- Nodes: {provider.nodes}\n"
            f"- Merge candidates: {provider.merge_candidates}"
        )
    sections = [
        f"Source: {markdown_text(source_path)}",
        "",
        "## Provider Delta To Shared Candidate Logic",
        "",
        f"![Provider delta to shared candidate logic]({figure_name})",
        "",
        "LLM latent vectors may change retrieval and ranking deltas. This figure "
        "keeps the decision boundary in the existing responsibility-scoped "
        "candidate logic.",
        "",
        "## Comparison Metrics",
        "",
        metric_table(facts.merge, facts.search.metric_cards),
        "",
        "## Reader Guide",
        "",
        "Inspect the primary figure first. Ratios are diagnostic overlap values: "
        "higher means the two providers returned more of the same top keys, "
        "lower means the provider changed retrieval or ranking. A lower overlap "
        "does not grant merge, deletion, labeling, or ownership authority.",
        "",
        "`candidate_logic_authority=shared_responsibility_bucket`",
        "",
        "## Provider Provenance",
        "",
        "\n\n".join(provider_sections),
        "",
        delta_markdown(facts.merge),
    ]
    if facts.search.delta is None:
        sections.extend(
            [
                "",
                "## Search Top Hits",
                "",
                "Search comparison was not recorded in the input JSON.",
            ]
        )
    else:
        sections.extend(["", delta_markdown(facts.search.delta)])
    if search:
        sections.extend(
            [
                "",
                "## Search Top Hits",
                "",
                markdown_list("Left top hits", object_string_list(search.get("left_top", []))),
                "",
                markdown_list("Right top hits", object_string_list(search.get("right_top", []))),
            ]
        )
    sections.extend(
        [
            "",
            "## Limitations",
            "",
            "This report renders the supplied compare-providers JSON only. It "
            "does not rerun indexing, validate candidate quality, or change "
            "semantic-index thresholds. Query text is not embedded in this "
            "report; query length was "
            f"{facts.search.query_chars} characters when the input recorded it.",
        ]
    )
    return "\n".join(sections) + "\n"


def search_display(report: JsonObject) -> SearchDisplay:
    """Return search facts when the source recorded a search comparison."""
    raw_search = as_object(report.get("search"))
    if not raw_search:
        return SearchDisplay(
            figure_text="search not recorded",
            metric_cards=(),
            delta=None,
            query_chars=0,
        )
    search = delta_summary("search", raw_search)
    return SearchDisplay(
        figure_text=f"search overlap {percent(search.overlap_ratio)}",
        metric_cards=search_metric_cards(search),
        delta=search,
        query_chars=as_int(raw_search.get("query_chars", 0)),
    )


def report_facts(report: JsonObject) -> ReportFacts:
    """Extract report facts from compare-providers JSON."""
    return ReportFacts(
        left=provider_summary(report, "left"),
        right=provider_summary(report, "right"),
        merge=delta_summary("merge candidates", report.get("merge_candidates", {})),
        search=search_display(report),
    )


def sha256_bytes(value: bytes) -> str:
    """Return the SHA256 identity used by the report readback."""
    return hashlib.sha256(value).hexdigest()


def print_result(payload: JsonObject) -> None:
    """Emit one machine-readable result alongside native renderer output."""
    print("SEMANTIC_PROVIDER_HTML_REPORT_RESULT=" + json.dumps(payload, sort_keys=True))


def failed(
    status: str, message: str, *, exit_code: int = 1, **fields: object
) -> int:
    """Report one owning stage failure without disguising its native status."""
    payload: JsonObject = {"status": status, "error": message, "exit_code": exit_code}
    payload.update(fields)
    print_result(payload)
    return exit_code if exit_code > 0 else 1


def main() -> int:
    """Render the provider report through the installed Quarto CLI."""
    args = build_parser().parse_args()
    source_path = args.compare_json.absolute()
    output_path = args.output.absolute()
    if output_path.suffix.lower() != ".html":
        return failed(
            "invalid_source",
            "--output must name an .html artifact",
            source=str(source_path),
        )
    try:
        source_bytes = source_path.read_bytes()
    except FileNotFoundError:
        return failed("missing_asset", "compare-providers JSON is missing", source=str(source_path))
    except OSError as exc:
        return failed("invalid_source", f"compare-providers JSON is unreadable: {exc}", source=str(source_path))
    try:
        decoded_source = source_bytes.decode("utf-8")
        parsed: object = json.loads(decoded_source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return failed(
            "invalid_source",
            f"compare-providers JSON is invalid: {exc}",
            source=str(source_path),
            source_sha256=sha256_bytes(source_bytes),
        )
    if not isinstance(parsed, dict):
        return failed(
            "invalid_source",
            "compare-providers JSON must contain an object",
            source=str(source_path),
            source_sha256=sha256_bytes(source_bytes),
        )
    report = cast(JsonObject, parsed)
    facts = report_facts(report)
    figure_bytes = render_primary_figure(
        facts.left, facts.right, facts.merge, facts.search.figure_text
    ).encode("utf-8")
    frontmatter = (
        "---\n"
        f"title: {json.dumps(args.title, ensure_ascii=False)}\n"
        "format:\n"
        "  html:\n"
        f"    embed-resources: {'true' if args.embed_resources else 'false'}\n"
        "execute:\n"
        "  enabled: false\n"
        "---\n\n"
    )
    project_config = "project:\n  type: default\n"
    config_sha256 = sha256_bytes(
        (project_config + frontmatter).encode("utf-8")
    )
    source_sha256 = sha256_bytes(source_bytes)
    asset_sha256 = sha256_bytes(figure_bytes)

    quarto = shutil.which("quarto")
    if quarto is None:
        return failed(
            "renderer_unavailable",
            "Quarto CLI is not available on PATH",
            source=str(source_path),
            source_sha256=source_sha256,
            config_sha256=config_sha256,
            asset_sha256=asset_sha256,
        )
    quarto_path = str(Path(quarto).resolve())
    try:
        quarto_version_result = subprocess.run(
            [quarto_path, "--version"], check=False, capture_output=True, text=True
        )
        pandoc_version_result = subprocess.run(
            [quarto_path, "pandoc", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return failed(
            "renderer_unavailable",
            f"Quarto CLI could not be started: {exc}",
            source=str(source_path),
            source_sha256=source_sha256,
            config_sha256=config_sha256,
            asset_sha256=asset_sha256,
        )
    if quarto_version_result.returncode != 0 or pandoc_version_result.returncode != 0:
        native_exit_code = (
            quarto_version_result.returncode
            if quarto_version_result.returncode != 0
            else pandoc_version_result.returncode
        )
        native_stderr = (
            quarto_version_result.stderr + pandoc_version_result.stderr
        ).strip()
        if native_stderr:
            print(native_stderr, file=sys.stderr)
        return failed(
            "renderer_unavailable",
            "Quarto or its embedded Pandoc version command failed",
            exit_code=native_exit_code,
            source=str(source_path),
            source_sha256=source_sha256,
            config_sha256=config_sha256,
            asset_sha256=asset_sha256,
            quarto_version_exit_code=quarto_version_result.returncode,
            pandoc_version_exit_code=pandoc_version_result.returncode,
            stderr=native_stderr,
        )

    repository_root = Path(__file__).resolve().parents[4]
    lychee_config = (
        repository_root / "tools" / "validation" / "documentation" / "config" / "lychee.toml"
    )
    lychee = shutil.which("lychee")
    if lychee is None or not lychee_config.is_file():
        return failed(
            "validation_failed",
            "the configured offline Lychee link validator is unavailable",
            source=str(source_path),
            source_sha256=source_sha256,
            config_sha256=config_sha256,
            asset_sha256=asset_sha256,
            quarto_version=quarto_version_result.stdout.strip(),
            pandoc_version=pandoc_version_result.stdout.strip(),
        )

    source_hash = source_sha256
    config = {
        "title": args.title,
        "project": {"type": "default"},
        "format": "html",
        "embed-resources": args.embed_resources,
        "execute": {"enabled": False},
    }
    with tempfile.TemporaryDirectory(
        prefix="semantic-provider-html-report-"
    ) as temporary:
        workspace = Path(temporary)
        source_directory = workspace / "source"
        render_directory = source_directory / "rendered"
        source_directory.mkdir()
        (source_directory / "_quarto.yml").write_text(
            project_config,
            encoding="utf-8",
        )
        source_document = source_directory / "semantic-provider-report.qmd"
        inspect_output = workspace / "quarto-inspect.json"
        source_document.write_text(
            frontmatter
            + render_markdown_document(
                report, facts, source_path, "provider-delta.svg"
            ),
            encoding="utf-8",
        )
        figure_path = source_directory / "provider-delta.svg"
        figure_path.write_bytes(figure_bytes)

        inspect_argv = [
            quarto_path,
            "inspect",
            str(source_document),
            str(inspect_output),
        ]
        try:
            inspect_result = subprocess.run(
                inspect_argv,
                cwd=source_directory,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return failed(
                "renderer_unavailable",
                f"Quarto inspect could not be started: {exc}",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                quarto_version=quarto_version_result.stdout.strip(),
                pandoc_version=pandoc_version_result.stdout.strip(),
            )
        if inspect_result.stderr.strip():
            print(inspect_result.stderr, file=sys.stderr)
        if inspect_result.returncode != 0:
            return failed(
                "invalid_source",
                "Quarto inspect rejected the generated source or configuration",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                exit_code=inspect_result.returncode,
                stdout=inspect_result.stdout.strip(),
                stderr=inspect_result.stderr.strip(),
            )
        try:
            inspect_data: object = json.loads(inspect_output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return failed(
                "invalid_source",
                f"Quarto inspect returned unreadable JSON: {exc}",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
            )
        if not isinstance(inspect_data, dict):
            return failed(
                "invalid_source",
                "Quarto inspect did not return a JSON object",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
            )
        inspect_document = cast(JsonObject, inspect_data)
        resources_value = inspect_document.get("resources")
        if not isinstance(resources_value, list):
            return failed(
                "invalid_source",
                "Quarto inspect did not return its resource list",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
            )
        if any(not isinstance(item, str) for item in resources_value):
            return failed(
                "invalid_source",
                "Quarto inspect returned an unsupported resource entry",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
            )
        resources = cast(list[str], resources_value)
        external_resources = [
            item
            for item in resources
            if urlsplit(item).scheme in {"http", "https"} or urlsplit(item).netloc
        ]
        if external_resources:
            return failed(
                "validation_failed",
                "generated report resources must be local to keep rendering offline",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                resources=resources,
                external_resources=external_resources,
            )
        missing_resources = []
        for resource in resources:
            resource_path = Path(resource)
            if not resource_path.is_absolute():
                resource_path = source_directory / resource_path
            if not resource_path.is_file():
                missing_resources.append(resource)
        # Inspect does not enumerate every inline image; this renderer owns this SVG.
        if not figure_path.is_file() and figure_path.name not in missing_resources:
            missing_resources.append(figure_path.name)
        if missing_resources:
            return failed(
                "missing_asset",
                "Quarto source has a missing local report asset",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                resources=resources,
                missing_resources=missing_resources,
            )

        render_argv = [
            quarto_path,
            "render",
            str(source_document),
            "--to",
            "html",
            "--output",
            output_path.name,
            "--output-dir",
            render_directory.name,
            "--no-execute",
        ]
        try:
            render_result = subprocess.run(
                render_argv,
                cwd=source_directory,
                check=False,
            )
        except OSError as exc:
            return failed(
                "renderer_unavailable",
                f"Quarto renderer could not be started: {exc}",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                argv=render_argv,
                quarto_version=quarto_version_result.stdout.strip(),
                pandoc_version=pandoc_version_result.stdout.strip(),
            )
        if render_result.returncode != 0:
            return failed(
                "render_failed",
                "Quarto render returned a failure status",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                argv=render_argv,
                exit_code=render_result.returncode,
            )
        rendered_html = render_directory / output_path.name
        if not rendered_html.is_file():
            return failed(
                "render_failed",
                "Quarto returned success without producing the requested HTML file",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                argv=render_argv,
                exit_code=render_result.returncode,
            )

        lychee_path = str(Path(lychee).resolve())
        link_check_argv = [
            lychee_path,
            "--config",
            str(lychee_config),
            "--no-progress",
            str(rendered_html),
        ]
        try:
            link_check_result = subprocess.run(
                link_check_argv,
                cwd=render_directory,
                check=False,
            )
        except OSError as exc:
            return failed(
                "validation_failed",
                f"Lychee link validation could not be started: {exc}",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                argv=render_argv,
                link_check_argv=link_check_argv,
                error_detail=str(exc),
            )
        if link_check_result.returncode != 0:
            return failed(
                "validation_failed",
                "Lychee rejected a local link or asset in the rendered HTML",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                inspect_argv=inspect_argv,
                argv=render_argv,
                link_check_argv=link_check_argv,
                exit_code=link_check_result.returncode,
            )

        render_assets = [
            path
            for path in sorted(render_directory.rglob("*"))
            if path.is_file() and path != rendered_html
        ]
        asset_records: list[dict[str, object]] = []
        for asset_path in render_assets:
            relative = asset_path.relative_to(render_directory)
            destination = output_path.parent / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_path, destination)
            copied_sha256 = sha256_bytes(destination.read_bytes())
            staged_sha256 = sha256_bytes(asset_path.read_bytes())
            if copied_sha256 != staged_sha256:
                return failed(
                    "validation_failed",
                    f"rendered asset readback differs after writing: {destination}",
                    source=str(source_path),
                    source_sha256=source_hash,
                    config_sha256=config_sha256,
                    asset_sha256=asset_sha256,
                    argv=render_argv,
                    output=str(output_path),
                )
            asset_records.append(
                {"path": str(destination), "sha256": copied_sha256}
            )
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered_html, output_path)
            output_sha256 = sha256_bytes(output_path.read_bytes())
        except OSError as exc:
            return failed(
                "validation_failed",
                f"rendered HTML could not be written or read back: {exc}",
                source=str(source_path),
                source_sha256=source_hash,
                config_sha256=config_sha256,
                asset_sha256=asset_sha256,
                argv=render_argv,
                output=str(output_path),
            )

    result: JsonObject = {
        "status": "rendered",
        "source": str(source_path),
        "source_sha256": source_hash,
        "config_sha256": config_sha256,
        "configuration": config,
        "asset_sha256": asset_sha256,
        "quarto_version": quarto_version_result.stdout.strip(),
        "pandoc_version": pandoc_version_result.stdout.strip(),
        "inspect_argv": inspect_argv,
        "argv": render_argv,
        "exit_code": render_result.returncode,
        "output": str(output_path),
        "output_sha256": output_sha256,
        "assets": asset_records,
        "resources": resources,
        "link_check_argv": link_check_argv,
        "validation": {
            "quarto_inspect": "pass",
            "local_resources": "pass",
            "lychee": "pass",
        },
    }
    print(f"SEMANTIC_PROVIDER_HTML_REPORT={output_path}")
    print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
