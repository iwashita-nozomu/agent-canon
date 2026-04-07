---
name: project-review
description: Use this skill for repo-wide review, inventory, workflow health, and tooling health.
---

# Project Review

1. Read `agents/skills/project-review.md`.
1. Run the review in phases: inventory, static health, workflow health, tooling health, worktree health, then follow-up decision.
1. Prefer `make agent-checks`, `make ci-quick`, and `bash scripts/run_comprehensive_review.sh` over ad hoc repo-wide probing.
1. Return `fix now`, `follow-up`, and `delete-ok` findings separately.
