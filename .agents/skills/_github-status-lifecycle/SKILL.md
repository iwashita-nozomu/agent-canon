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
   write authority, repository-defined TOML label mapping, and lifecycle facts
   are available.
2. Dispatch the canonical routine and its `GhStatusAdapter`; the shim contains
   no lifecycle state table, label taxonomy, or alternate mutation algorithm.
3. Reuse or publish the required evidence comment before the final transition,
   then preserve unrelated labels through per-label operations and readbacks.
4. Return typed transport, evidence, drift, partial-mutation, and final-readback
   outcomes with their code owner and responsibility scope.
5. Report success only after fresh remote readback matches the routine's exact
   desired managed-label predicate.

This private skill does not create labels, close Issues, approve or merge PRs,
or replace the public `pr-processing` workflow.
