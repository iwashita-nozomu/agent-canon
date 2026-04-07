# codex-cli

## Purpose

Codex の入口、読順、skill path、subagent path を固定します。

## Use When

- active agent が Codex
- 入口文書の順序を迷いたくない
- Codex-specific な補足が必要

## Read Order

1. `AGENTS.md`
1. `agents/README.md`
1. `agents/canonical/CODEX_WORKFLOW.md`
1. 必要なら `agents/canonical/CODEX_SUBAGENTS.md`

## Runtime Paths

- shared canon: `agents/`
- auto-discovery skill path: `.agents/skills/`
- Codex runtime config: `.codex/`
