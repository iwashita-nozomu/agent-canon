---
name: claude-code-cli
description: Use when the active agent is Claude Code and you need the repository-specific startup path, shared canon, Claude-only subagent path, and command conventions.
---

# Claude Code CLI

1. Start in the repository root.
1. Read `CLAUDE.md`, which imports shared rules from `AGENTS.md`.
1. Use `.claude/skills/` for Claude-compatible skill discovery.
1. Use `.claude/agents/` for Claude-native subagents.
1. Use Claude Code's `/agents` command to inspect or launch subagents when specialist delegation is needed.
1. Keep shared workflow truth in `agents/`, not in Claude-only prompts.
