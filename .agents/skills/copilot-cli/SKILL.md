---
name: copilot-cli
description: Use when the active agent is GitHub Copilot CLI or GitHub-hosted Copilot coding agent and you need the current repository-specific startup path without relying on retired gh-copilot patterns.
---

# Copilot CLI

1. Read `.github/copilot-instructions.md` first, then `AGENTS.md`.
1. Use `.agents/skills/` as the project skill path.
1. Treat `.github/copilot-instructions.md` as the repository-specific instruction source for Copilot.
1. Do not rely on legacy `gh-copilot` extension examples; GitHub-hosted coding agent can start from issues or pull requests, and local wrappers vary by installation.
1. Keep shared workflow and artifact rules in `agents/`.
