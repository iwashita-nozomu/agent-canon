---
name: python-review
description: Use when Python code changes need strict review for pyright, pytest, ruff, type boundaries, and API behavior.
---

Dependency Files:

- vendor/agent-canon/AGENTS.md
- vendor/agent-canon/.agents/skills/python-review/SKILL.md
- vendor/agent-canon/tools/docs/mirror_skill_shims.py
- vendor/agent-canon/documents/SKILL_IMPLEMENTATION_GUIDE.md

# Python Review

1. Read `agents/skills/python-review.md`.
1. Fix the changed Python files and related tests before validating.
1. Run or inspect `pyright`.
1. Run or inspect `pytest tests/`.
1. Run or inspect `ruff check python tests --select D,E,F,I,UP`.
1. Check API behavior, type boundaries, and docs/test follow-through.
1. Report findings before summaries.
