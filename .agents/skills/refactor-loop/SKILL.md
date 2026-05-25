---
name: refactor-loop
description: Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates.
---
<!--
@dependency-start
responsibility Documents Refactor Loop for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable refactor structure contracts
@dependency-end
-->


# Refactor Loop

1. Read `agents/skills/refactor-loop.md`.
1. Use `$structure-planning` before editing when file moves, module boundaries, repair slices, path mapping, responsibility maps, allowed structural delta, or forbidden semantic delta are nontrivial.
1. Fix `Behavior Contract`, `Allowed Structural Delta`, and `Forbidden Semantic Delta` before editing.
1. Record delete, move, rename, and split targets before implementation.
1. Keep feature additions out of the same pass.
1. For dependency-guided structural duplicate cleanup, generate `priority_order`
   and `repair_slice`, fix one slice at a time, expand downstream affected files,
   reject responsibility-mixing root findings as `review_required`, and rerun the
   full scan after each slice before choosing the next slice.
1. For non-trivial refactors, route implementation and review to separate
   subagents: parent fixes the contract and artifacts, one write-capable
   `worker`/`spark_worker` implements, `test_designer` defines regression
   coverage before code changes, and a separate read-only reviewer
   (`python_reviewer`, `cpp_reviewer`, or `reviewer`) reviews the latest diff
   with before/after scan and impact evidence.
1. Run `test_designer` before implementation and keep regression coverage in the same pass.
1. If file structure changes, plan the integration check with `python3 tools/ci/check_merge_structure.py ...`.
