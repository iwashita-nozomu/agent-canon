---
name: test-design
description: Use when code changes need adversarial static test design before implementation.
---
<!--
@dependency-start
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Test Design

1. Read `agents/skills/test-design.md`.
1. Fix the target code paths and related test paths.
1. Statically inspect branches, parsing, error handling, and state transitions.
1. Record nasty edge cases and regression cases in `test_plan.md`.
1. Keep cases concrete: target, input, expected outcome, and why the case is nasty.
1. Mirror existing test style, fixture layout, and naming before suggesting anything new.
