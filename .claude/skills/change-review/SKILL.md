---
name: change-review
description: Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions.
---
<!--
@dependency-start
@dependency-end
-->


# Change Review

1. Read `agents/skills/change-review.md`.
1. Review the actual diff first.
1. Report findings before summaries.
1. Prioritize:
   - behavioral regressions
   - missing validation
   - missing tests
   - stale documentation
1. Separate `fix now` from `follow-up`.
1. Use `documents/REVIEW_PROCESS.md` for repo review expectations.
