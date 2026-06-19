# References
<!--
@dependency-start
contract reference
responsibility Indexes AgentCanon reference material used by workflows, reviews, and research notes.
upstream design ../agents/workflows/workflow-references.md cites workflow-level sources
downstream design agent-canon-technology-bibliography.md catalogs implementation/runtime technical sources
downstream design ../documents/experiment-critical-review.md points reviewers to reference context
downstream design ../documents/experiment-report-style.md points report authors to reference context
@dependency-end
-->

This directory holds durable reference material that supports AgentCanon
workflow, review, and research guidance. If an agent consults an external PDF
or HTML source, the source URL must be registered here as a Markdown reference
file before the work is closed.

Use `agents/workflows/workflow-references.md` for workflow-level bibliography
and source notes. Put large external artifacts outside the tracked tree unless a
task explicitly requires a small, redistributable reference file.

Before adding a new source note, search the existing `references/`, `notes/`,
`documents/`, and topic reports for the same title, DOI, URL, or claim. Update
or cite the existing note when one exists.

## Indexes

- [AgentCanon Technology Bibliography](agent-canon-technology-bibliography.md)
  maps implementation and runtime surfaces to consulted technical sources.
- [Workflow references](../agents/workflows/workflow-references.md) indexes
  workflow, review, research, and reporting sources.

When a task uses an external source in an answer, report, design, benchmark, or
workflow rule, leave a durable source record. At minimum record URL or DOI,
access date, the claim used, known limitations, adoption or exclusion decision,
and whether a downloaded artifact was retained or intentionally left outside the
tracked tree.

## External PDF / HTML Capture

Use the reference materializer for consulted PDF or HTML sources:

```bash
python3 tools/agent_tools/reference_materializer.py \
  --url "https://example.com/source.pdf" \
  --input /path/to/downloaded-source.pdf
```

The output is a Markdown file under `references/external/` with source URL,
kind, retrieval time, content hash, extraction method, and extracted text. HTML
sources are acceptable when they carry the same source material as the PDF.

The Codex reference-capture hook logs observed source URLs and blocks
PostToolUse / Stop events when a consulted URL is not present in
`references/**/*.md`. UserPromptSubmit events are logged without blocking so
later dashboard and prompt-eval work can measure which prompts created
reference-capture obligations.
