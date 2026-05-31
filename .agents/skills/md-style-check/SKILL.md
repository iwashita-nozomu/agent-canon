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
1. Check `documents/conventions/common/05_docs.md`.
1. Treat plain `md-style-check` or `$md-style-check` in a user request as an explicit skill invocation, not only a candidate signal.
1. Select this skill when a repo-changing task edits Markdown files or routes docs lint, link, heading, markdown math, or docs-check failures.
1. Run markdown lint and link checks appropriate to the changed files.
1. When markdown math drift appears, run `python3 tools/docs/check_markdown_math.py <paths>` and use `python3 tools/docs/fix_markdown_math.py <paths>` only for mechanical delimiter repair.
1. Check heading hierarchy, command/path formatting, and broken links together.
1. Treat broken links and heading drift as real findings.
