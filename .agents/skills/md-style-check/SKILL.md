---
name: md-style-check
description: Use when Markdown files changed, docs formatter/fixer output must be checked, or `agent-canon docs` formatting, heading, math, Mermaid, and link checks are in scope.
---

<!--
@dependency-start
contract skill
responsibility Documents Markdown Style Check for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->

# Markdown Style Check

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill md-style-check --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/md-style-check.md`.
1. Check `documents/coding-conventions-project.md` and
   `documents/conventions/common/05_docs.md`.
1. Treat plain `md-style-check` or `$md-style-check` in a user request as an explicit skill invocation, not only a candidate signal.
1. Select this skill when a repo-changing task edits Markdown files or routes docs lint, link, heading, Mermaid, markdown math, docs-check, formatter, or `agent-canon docs` failures.
1. Treat this skill as the Markdown checker route for typo/link/format-only edits. Pair it with `$owner-bounded-routing` when the whole task is an owner-bounded repository edit. When a Markdown change alters section order, reader path, claim support, source map, canonical route, or document responsibility, add `$prose-reasoning-graph` and `$structure-planning` before prose edits; for the format-only route, record `structure_contract=skipped` with the reason.
1. For typo/link/format-only edits, do not require runtime `SKILL.md` reading
   before running the docs tool or patching. Keep owner, existing-tool route,
   and targeted-validation evidence.
1. Use the unified Rust entrypoint as the canonical tool: `tools/bin/agent-canon docs check <paths...>` for checks and `tools/bin/agent-canon docs format <paths...>` for formatter repairs.
1. Use `tools/bin/agent-canon docs -h` for command options and examples before reading implementation files.
1. Before formatting files with display math, normalize display math to standalone double-dollar delimiter lines with blank lines around the block. Do not nest Markdown display delimiters inside KaTeX / math fenced blocks.
1. Inline math in prose must use `$...$` (for example, `$(式)$`). Do not put math in inline code backticks, and do not use double-dollar display delimiters inside a sentence. Reserve double-dollar delimiters for display math on standalone delimiter lines.
1. For tool-covered Markdown style, link, heading, math, and Mermaid properties, run the Rust docs tool before reading whole documents or spawning reviewers. Trust `DOCS_CHECK=pass`, `DOCS_CHECK_FINDING=...`, and the `DOCS_CHECK_REPORT_BEGIN` structured report; open only the reported path and nearby lines when a repair needs prose context.
1. After any docs formatter or fixer runs, treat the adjacent check as part of the same operation: run `tools/bin/agent-canon docs check <paths...>` or record why the command was unavailable.
1. Use `tools/bin/agent-canon docs fix-math <paths...>` and `tools/bin/agent-canon docs fix-mermaid <paths...>` for mechanical math or Mermaid repairs.
1. If the docs formatter or fixer escapes display delimiters or creates duplicate display delimiters, repair the block form and rerun `tools/bin/agent-canon docs check <paths...>`.
1. Check heading hierarchy, command/path formatting, Mermaid fenced blocks, markdown math, and broken links together.
1. Treat broken links and heading drift as real findings.
1. Last, inspect formatter-sensitive inline math and inline code in tables. A table cell must not contain a raw `|` inside backticks or inline math; if the formatter escapes backticks or splits a cell, split the expression out of the table, replace the cell with a short name, or otherwise repair the rendered Markdown, then rerun `tools/bin/agent-canon docs check <paths...>`.
1. If a docs formatter/fixer/checker failure drives repair, record the
   validation-failure-response packet (`failing_contract`, `observation_level`,
   `cause_classification`, `intent_preservation`, and `evidence`). Use
   `intent_preservation` for the same-intent repair / owner-route repair /
   residual classification / escalation route. Do not close a docs-check failure by
   pass-only scope shrink, link/heading oracle weakening, or validation
   downscope.
