---
name: _github-status-lifecycle
description: "Runtime-internal skill used by pr-processing to reconcile GitHub Issue status labels, evidence comments, concurrency, and final readback without changing unrelated metadata."
---

<!--
@dependency-start
contract skill
responsibility Exposes deterministic GitHub Issue status lifecycle reconciliation as a private runtime skill.
upstream design ../../../agents/internal-routines/github-status-lifecycle.md canonical lifecycle, evidence, failure, and readback owner
upstream design ../../../agents/skills/pr-processing.md public caller and GitHub publication owner
@dependency-end
-->

# _github-status-lifecycle

## Canonical Routine

Canonical lifecycle and policy:
`agents/internal-routines/github-status-lifecycle.md`.

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill _github-status-lifecycle --format text`
<!-- skill-tool-commands:end -->

## Invocation Boundary

1. Invoke only from `pr-processing` after the target Issue, fresh remote state,
   write authority, repository-defined label mapping, and lifecycle facts are
   available.
2. Compute a desired managed-label set; never toggle labels or infer progress
   from the current label alone.
3. Publish or reuse the required evidence comment before the final transition.
4. Preserve unrelated labels and stop on concurrent drift or partial mutation.
5. Report success only after fresh remote readback matches the exact desired
   managed-label set.

This private skill does not create labels, close Issues, approve or merge PRs,
or replace the public `pr-processing` workflow.
