---
name: md-style-check
description: Use when Markdown files changed and you need formatting, heading, and link checks aligned with the repository's documentation rules.
---

<!--
@dependency-start
responsibility Documents Markdown Style Check for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->

# Markdown Style Check

1. Read `agents/skills/md-style-check.md`.
1. Check `documents/coding-conventions-project.md` and
   `documents/conventions/common/05_docs.md`.
1. Treat plain `md-style-check` or `$md-style-check` in a user request as an explicit skill invocation, not only a candidate signal.
1. Select this skill when a repo-changing task edits Markdown files or routes docs lint, link, heading, markdown math, or docs-check failures.
1. Before formatting files with display math, normalize display math to standalone double-dollar delimiter lines with blank lines around the block. Do not nest Markdown display delimiters inside KaTeX / math fenced blocks.
1. Run the repo-local formatter first: `python3 tools/docs/format_markdown.py <changed Markdown files>`.
1. Run `mdformat <changed Markdown files>`, then `mdformat --check <changed Markdown files>`.
1. Run markdown lint and link checks appropriate to the changed files.
1. When markdown math drift appears or touched files contain display math delimiters, run `python3 tools/docs/check_markdown_math.py <paths>` and use `python3 tools/docs/fix_markdown_math.py <paths>` only for mechanical delimiter repair.
1. If `mdformat` escapes display delimiters or creates duplicate display delimiters, repair the block form and rerun `mdformat`, `mdformat --check`, and `check_markdown_math.py`.
1. Check heading hierarchy, command/path formatting, and broken links together.
1. Treat broken links and heading drift as real findings.
1. Last, inspect formatter-sensitive inline math and inline code in tables. A table cell must not contain a raw `|` inside backticks or inline math; if `mdformat` escaped backticks, split the expression out of the table, replace the cell with a short name, or otherwise repair the rendered Markdown, then rerun `mdformat`, `mdformat --check`, and `check_markdown_math.py`.
