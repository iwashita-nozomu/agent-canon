---
name: md-style-check
description: Use when Markdown files changed, docs formatter/fixer output must be checked, or `agent-canon docs` formatting, heading, math, Mermaid, and link checks are in scope.
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
1. Select this skill when a repo-changing task edits Markdown files or routes docs lint, link, heading, Mermaid, markdown math, docs-check, formatter, `format_markdown.py`, or `agent-canon docs` failures.
1. Use the unified Rust entrypoint as the canonical tool: `tools/bin/agent-canon docs check <paths...>` for checks and `tools/bin/agent-canon docs format <paths...>` for formatter repairs.
1. For tool-covered Markdown style, link, heading, math, and Mermaid properties, run the Rust docs tool before reading whole documents or spawning reviewers. Trust `DOCS_CHECK=pass` / `DOCS_CHECK_FINDING=...`; open only the reported path and nearby lines when a repair needs prose context.
1. After any docs formatter or fixer runs, treat the adjacent check as part of the same operation: run `tools/bin/agent-canon docs check <paths...>` or record why the command was unavailable.
1. Use `tools/bin/agent-canon docs fix-math <paths...>` and `tools/bin/agent-canon docs fix-mermaid <paths...>` for mechanical math or Mermaid repairs.
1. Check heading hierarchy, command/path formatting, Mermaid fenced blocks, markdown math, and broken links together.
1. Treat broken links and heading drift as real findings.
