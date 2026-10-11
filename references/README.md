# References
<!--
@dependency-start
contract reference
responsibility Indexes AgentCanon reference material used by workflows, reviews, and research notes.
upstream design ../agents/workflows/workflow-references.md cites workflow-level sources
downstream design agent-canon-technology-bibliography.md catalogs implementation/runtime technical sources
downstream design gpt-5.6-benchmark-report-ja.md records the dated GPT-5.6 model-family benchmark and routing study
downstream design ../documents/experiments/experiment-critical-review.md points reviewers to reference context
downstream design ../documents/experiments/experiment-report-style.md points report authors to reference context
@dependency-end
-->

This directory holds durable reference material that supports AgentCanon
workflow, review, and research guidance. If an agent consults an external PDF
or HTML source, the source URL must be registered here as a Markdown reference
file before the work is closed.

Use [agents/workflows/workflow-references.md](../agents/workflows/workflow-references.md) for workflow-level bibliography
and source notes. Put large external artifacts outside the tracked tree unless a
task explicitly requires a small, redistributable reference file.

Before adding a new source note, search the existing `references/`, `documents/notes/`,
`documents/`, and topic reports for the same title, DOI, URL, or claim. Update
or cite the existing note when one exists.

## Indexes

- [AgentCanon Technology Bibliography](agent-canon-technology-bibliography.md)
  maps implementation and runtime surfaces to consulted technical sources.
- [GPT-5.6 benchmark and routing study](gpt-5.6-benchmark-report-ja.md)
  records the dated Japanese benchmark interpretation and heterogeneous
  multi-agent routing proposal.
- [Workflow references](../agents/workflows/workflow-references.md) indexes
  workflow, review, research, and reporting sources.

When a task uses an external source in an answer, report, design, benchmark, or
workflow rule, leave a durable source record. At minimum record URL or DOI,
access date, the claim used, known limitations, adoption or exclusion decision,
and whether a downloaded artifact was retained or intentionally left outside the
tracked tree.

## DOI Metadata Capture

When a DOI is already known, run this lookup from the host shell to retrieve
bibliographic metadata from Crossref as raw CSL JSON:

```bash
bash tools/analysis/documents/literature_metadata.sh "10.1234/example.doi" \
  > /tmp/example.csl.json 2> /tmp/example.provenance.md
```

The host shell is the network caller for this command; it does not change the
shared tool runtime's network configuration. It sends the DOI to Crossref's
versioned `/v1/works/{doi}/transform` route with
`Accept: application/vnd.citationstyles.csl+json`. It writes the
provider response bytes unchanged to stdout and writes provider, DOI, request
URL, retrieval time, request digest, and response digest to stderr. It uses the
host's existing `curl` and a host `sha256sum` or `shasum`; it does not perform
broader discovery, maintain a cache, or fetch full text. The request digest
covers the GET method, Accept header, and exact encoded request URL. A failed
HTTP request exits nonzero without writing response bytes.

Keep the raw response only when it is useful to the research record, and record
its path and the provenance fields in the existing Markdown source note. Add
the claim used, limitations, and adoption or exclusion decision there as usual.
The Crossref REST API serves metadata deposited by members, so verify the source
identity against the publication and do not treat metadata as evidence for its
claims. See [Crossref content negotiation](https://www.crossref.org/documentation/retrieve-metadata/content-negotiation/)
for the CSL media type and single-record response, and the
[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
for its metadata source (both accessed 2026-10-11).

## External PDF / HTML Capture

Use the reference materializer for consulted PDF or HTML sources:

```bash
AGENT_CANON_PARENT_ROOT=/abs/path/to/parent-repository \
python3 tools/analysis/documents/reference_materializer.py \
  --url "https://example.com/source.pdf" \
  --input /path/to/downloaded-source.pdf
```

`AGENT_CANON_PARENT_ROOT` must name the authenticated Git repository that owns
the reference output. The materializer has no source-checkout or `$HOME`
fallback: without this explicit parent capability it fails before creating a
file. Runtime logs, temporary downloads, and extracted intermediates remain in
the external runtime root; only the requested Markdown source record is
published into the parent-owned `references/` tree.

The output is a Markdown file under `references/external/` with source URL,
kind, retrieval time, content hash, extraction method, and extracted text. HTML
sources are acceptable when they carry the same source material as the PDF.

The Codex reference-capture hook logs observed source URLs and blocks
PostToolUse / Stop events when a consulted URL is not present in
`references/**/*.md`. UserPromptSubmit events are logged without blocking so
later dashboard and prompt-eval work can measure which prompts created
reference-capture obligations.
