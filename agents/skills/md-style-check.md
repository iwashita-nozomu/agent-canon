# md-style-check

<!--
@dependency-start
contract skill
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../ROOT_AGENTS.md shared post-edit formatting boundary
upstream design ../../documents/design/formatting.md final edited and validated content correspondence
upstream design code-visualization.md sole public visualization owner and typed projection contract
upstream design report-writing.md report evidence and optional structure boundary
upstream design structure-planning.md actual structural decision owner
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md responsibility-owned validation selection
downstream implementation ../../tests/tools/test_fix_mermaid.py tests native Mermaid syntax checks
@dependency-end
-->

## Reader Map

- Purpose: keep changed Markdown aligned with the document owner's formatting and
  link rules.
- Use when: Markdown changed, docs format/check is selected, or a docs-check
  finding needs repair.
- Boundary: the document owner decides meaning and evidence; this skill handles
  formatting, headings, links, math, Mermaid, and the selected formatter route.

## Procedure

Run `agent-canon docs format --root . <edited paths...>` with `markdownlint-cli2`
available and inspect the final diff. The
[formatter settings](../../documents/design/formatting.md#markdown-execution)
describe how to use the shared environment when it exposes source read-only.

For Markdown intended for GitHub, run `agent-canon docs check --root . <edited paths...>`.
Run it directly in the existing [shared tool runtime](agent-canon-bootstrap.md).
Resolve missing image providers through the shared image installation.
Use the edited checkout or a snapshot with the same content. The check runs
lint and link checks, parses GitHub Flavored Markdown, and renders Mermaid
blocks.

For a requested equation preview, render the expressions with an available
renderer that supports the source syntax. If Pandoc's MathML writer cannot
render an expression, try the shared image's `katex` command.
Name the renderer used. Inspect GitHub's preview for changes that depend on
hosted rendering when the preview is available. Record any remaining verification
gaps with the reason.

## Boundary

Use `structure-planning`, docs completeness/consistency review, or report-writing
only when the changed document owner selects them for a real structural or
reader-facing decision.

## Core References

- [`coding-conventions-project.md`](../../documents/conventions/coding-conventions-project.md)
- [`05_docs.md`](../../documents/conventions/common/05_docs.md)
- [`.markdownlint-cli2.jsonc`](../../.markdownlint-cli2.jsonc)
- [`dependencies.toml`](../../bootstrap/container/image/dependencies.toml)
- `tools/runtime/dispatch/agent-canon/src/docs.rs`
