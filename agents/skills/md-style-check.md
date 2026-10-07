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

1. Identify the changed Markdown owner and select its existing formatter/check
   route. Project documentation uses its project route; AgentCanon examples apply
   only when the AgentCanon owner selects them.
2. Read the selected command's help when options are needed, then run the chosen
   format/check command through the existing tool owner. A Markdown edit alone
   does not require an AgentCanon checker.
3. If the report identifies a path, read that path and nearby lines. Repair only
   the reported formatting, link, heading, math, or Mermaid property; route
   semantic or cross-document issues to the document owner.
4. Use the selected formatter/fixer for math or Mermaid when available. Keep
   display math on standalone `$$` lines, inline math in `$...$`, and literal
   commands/paths in code spans; do not add formatter-specific conventions beyond
   the repository's existing docs rules.
5. Rerun the same owner's required check after a formatter/fixer edit, reusing an
   adjacent result already produced by that command. Do not repeat a check or
   widen to full review when it cannot change the selected property.
6. Inspect the final diff for broken links, heading drift, table/code readability,
   and preservation of document meaning. A formatter pass is not evidence that
   content is correct.

## Boundary

Use `structure-planning`, docs completeness/consistency review, or report-writing
only when the changed document owner selects them for a real structural or
reader-facing decision. This skill does not create a second checklist, schema,
approval gate, or validation-failure packet; failed checks follow the existing
failure owner.

## Core References

- [`coding-conventions-project.md`](../../documents/conventions/coding-conventions-project.md)
- [`05_docs.md`](../../documents/conventions/common/05_docs.md)
- `.markdownlint.json`
- `tools/runtime/dispatch/agent-canon/src/docs.rs`
