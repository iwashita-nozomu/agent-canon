# md-style-check

<!--
@dependency-start
contract skill
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../ROOT_AGENTS.md shared post-edit formatting boundary
upstream design agent-canon-bootstrap.md shared runtime and registered target execution
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

1. Identify the changed Markdown paths and content owner. This binds the
   operation and returned findings to the requested scope.
2. Run AgentCanon's native
   `agent-canon docs format --root . <changed Markdown paths...>` through the
   [shared runtime route](agent-canon-bootstrap.md#command-shape), with the
   registered target as the working directory. This entrypoint applies the
   configured formatter and checks together on the selected files. Read help
   only when an option remains unresolved. If a provider requires writable
   cache or temporary output, place a task-specific directory under
   `AGENT_CANON_RUNTIME_ROOT` and pass it through that invocation's supported
   environment variable. The registered target or private home may be
   read-only, so generated state belongs outside them under the
   [shared runtime boundary](agent-canon-bootstrap.md#command-shape).
3. Inspect the formatter's changes and diagnostics, then repair relevant
   formatting, link, heading, math, or Mermaid findings. The formatter
   normalizes line endings, trailing whitespace, and repeated blank lines; it
   does not decide the correctness of claims or mathematical/diagram meaning.
   The content owner handles semantic and cross-document findings for that
   reason.
4. After repairs or later edits, rerun the formatter on the changed scope and
   inspect the final diff for readability and meaning. Retain the actual
   command, diagnostics, exit status, and remaining verification limits.
   Earlier results do not cover subsequent edits, so this keeps the
   [edited, validated, and submitted content](../../documents/design/formatting.md#engineering-rationale)
   aligned.

The AgentCanon docs route invokes the configured `markdownlint-cli2` and offline
`lychee` providers directly, then uses Quarto's embedded Pandoc AST for
workspace-absolute local-target policy and Mermaid-block selection. `mmdc`
validates Mermaid syntax in a temporary output directory without rewriting the
source. The repository-specific residuals are per-depth unordered-marker
consistency, exact math delimiter spelling, bootstrap documentation, and the
runtime-profile inventory. Standard-tool output and exit status remain native.

## Boundary

Use `structure-planning`, docs completeness/consistency review, or report-writing
only when the changed document owner selects them for a real structural or
reader-facing decision. This skill does not create a second checklist, schema,
approval gate, or validation-failure packet; failed checks follow the existing
failure owner.

## Core References

- [`coding-conventions-project.md`](../../documents/conventions/coding-conventions-project.md)
- [`05_docs.md`](../../documents/conventions/common/05_docs.md)
- [`.markdownlint-cli2.jsonc`](../../.markdownlint-cli2.jsonc)
- [`dependencies.toml`](../../bootstrap/container/image/dependencies.toml)
- `tools/runtime/dispatch/agent-canon/src/docs.rs`
