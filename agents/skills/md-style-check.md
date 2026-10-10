# md-style-check

<!--
@dependency-start
contract skill
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../ROOT_AGENTS.md shared post-edit formatting boundary
upstream design code-visualization.md sole public visualization owner and typed projection contract
upstream design report-writing.md report evidence and optional structure boundary
upstream design structure-planning.md actual structural decision owner
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md responsibility-owned validation selection
downstream implementation ../../tests/tools/test_fix_mermaid.py tests formatter and post-format coverage behavior
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

Identify the changed Markdown owner and use its existing formatter/check route.
Read command help when an option is needed; a Markdown edit alone does not imply
an AgentCanon checker. If a check reports a path, inspect the relevant text and
repair that formatting, link, heading, math, or Mermaid issue. Route semantic or
cross-document findings to the content owner.

The AgentCanon docs route uses the pinned `markdownlint-cli2` configuration at
`.markdownlint-cli2.jsonc` for heading increments, trailing spaces, hard tabs,
list spacing, and fenced-code languages. Per-depth unordered-marker consistency
remains repository-specific because the standard `sublist` rule also requires
parent and child markers to differ. Use `agent-canon docs check` so these
provider findings stay composed with the repository's local-link, math,
bootstrap-documentation, and runtime-profile checks.
The `0.17.2` pin reuses the shared Node 18 runtime; `0.23.3` requires Node 22,
which is outside this documentation-check migration.

Use the selected math/Mermaid formatter when available. Preserve existing
delimiter and literal-command conventions. After a formatter/fixer edit, rerun
the same required check when it can establish the corrected property, reusing a
nearby result from that command. Inspect the final change for readability and
meaning: formatting success alone does not establish content correctness.

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
