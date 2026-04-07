---
name: python-review
description: Use when Python code changes need strict review for pyright, pytest, ruff, type boundaries, and API behavior.
---

# Python Review

1. Read `agents/skills/python-review.md`.
1. Fix the changed Python files and related tests before validating.
1. Run or inspect `pyright`.
1. Run or inspect `pytest python/tests/`.
1. Run or inspect `ruff check python/ --select D,E,F,I,UP`.
1. Check API behavior, type boundaries, and docs/test follow-through.
1. Report findings before summaries.
