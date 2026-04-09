---
name: behavior-preserving-refactor
description: Use when a large refactor should be treated as behavior-preserving structural change with explicit path mapping, semantic-delta controls, and strong review gates.
---

# Behavior Preserving Refactor

1. Read `agents/skills/behavior-preserving-refactor.md`.
1. Fix `Behavior Contract`, `Allowed Structural Delta`, and `Forbidden Semantic Delta` before editing.
1. Record delete, move, rename, and split targets before implementation.
1. Keep feature additions out of the same pass.
1. Run `test_designer` before implementation and keep regression coverage in the same pass.
1. If file structure changes, plan the integration check with `python3 scripts/ci/check_merge_structure.py ...`.
