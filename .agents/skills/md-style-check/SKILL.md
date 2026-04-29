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
1. Run markdown lint and link checks appropriate to the changed files.
1. Check heading hierarchy, command/path formatting, and broken links together.
1. Treat broken links and heading drift as real findings.
