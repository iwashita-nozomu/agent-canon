---
name: refactor-loop
description: Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates.
---
<!--
@dependency-start
responsibility Documents Refactor Loop for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable refactor structure contracts
upstream design ../../../agents/skills/dependency-analysis.md defines change-impact and repair-planning packets
upstream design ../../../agents/skills/tool-finding-report.md tool-based finding packet workflow
@dependency-end
-->


# Refactor Loop

1. Start from the dependency-expanded scope, not from the initially mentioned
   file. The editable candidate set is every file returned by dependency
   analysis for the requested object/file, plus tests and docs required by
   those dependencies. Narrow implementation only after mapping exact target
   functions, methods, and classes inside that expanded scope.
1. Use `$dependency-analysis` to create a token-light `Change Impact Packet`
   manifest before choosing targets, writing the refactor orchestration plan,
   or launching a write-capable subagent. The packet is the unified
   repair-planning input; raw findings, raw search hits, and single filenames
   are not enough. Full dependency artifacts stay on disk and are read only for
   the current repair batch or disputed edges.
1. Before launching implementation subagents, the parent must write a refactor
   orchestration plan from that dependency graph. Separate sequential root
   slices that must be fixed first from independent downstream slices that can
   run in parallel, assign each target object to an owner/wave, and record
   `blocked_by`, allowed files, validation, and whether the slice is single-agent
   or parallel-safe.
1. Choose repair scope granularity from tool-generated `scope_candidates`, not
   from a fixed file/function rule. Optimize for the fewest coherent writer
   waves and tool reruns while preserving behavior contract clarity, write-scope
   isolation, token budget, validation surface, and semantic-risk boundaries.
1. The default implementation handoff is a dependency-expanded repair batch,
   not a single finding. Group every mechanically safe target in the same
   responsibility group, dependency wave, and validation surface into one
   object-by-object handoff. A single-finding handoff is allowed only for
   root/shared contract changes, risky semantic changes, or when the
   orchestration plan records why related targets are `review_required` or
   deferred.
1. Read `agents/skills/refactor-loop.md`.
1. Use `$structure-planning` before editing when file moves, module boundaries, repair slices, path mapping, responsibility maps, allowed structural delta, or forbidden semantic delta are nontrivial.
1. Fix `Behavior Contract`, `Allowed Structural Delta`, and `Forbidden Semantic Delta` before editing.
1. For API-shaping refactors, fix `Expected API` before editing and pass that
   expected API in every subagent handoff. Do not split the work merely to keep
   the repository runnable after each intermediate edit; per-step operation
   checks are not required until the user-facing return gate, where the final
   intended API and all updated call sites must be validated together.
1. Explicitly list every function, method, or class being changed before editing, using `path:start-end:qualname`; do not start implementation from a file-level or module-level target alone.
1. If a shared policy or base abstraction is being consolidated, first declare the canonical module/object, refactor that root surface, then run dependency and usage scans before touching dependents.
1. Record delete, move, rename, and split targets before implementation.
1. Keep feature additions out of the same pass.
1. For dependency-guided structural duplicate cleanup, generate `priority_order`
   and `repair_slice` through `$tool-finding-report`, fix one
   dependency-expanded repair batch/wave at a time, feed the finding packet
   into `$dependency-analysis` to join code/header/search impact and generate
   tool-made `impact_blocks`, expand downstream affected files, reject
   responsibility-mixing root findings as `review_required`, and rerun the full
   scan after each batch before choosing the next batch.
1. After each implementation slice, join the latest `git diff` against the full
   finding packet. Produce a `diff_linked_findings` artifact that separates
   direct changed-line findings, related structural findings for changed
   functions/classes and their dependency/representative instances, and
   unchanged out-of-slice findings.
1. Use `$tool-finding-report` before implementation and after each slice to
   preserve baseline, structured findings, impact, and prompt feedback decision;
   repair `handoff_prompt_gap` or `shared_skill_or_workflow_gap` before launching
   the next write-capable subagent.
1. For non-trivial refactors, route implementation and review to separate
   subagents: parent fixes the contract and artifacts, one or more
   wave-scoped write-capable `worker`/`spark_worker` agents implement,
   `test_designer` defines regression coverage before code changes, and a
   separate read-only reviewer
   (`python_reviewer`, `cpp_reviewer`, or `reviewer`) reviews the latest diff
   with before/after scan, impact evidence, and `diff_linked_findings`.
   Low-level dependency/root slices run first with the fewest write-capable
   agents. Conflict risk must be resolved by task order, not by shrinking the
   repair batch to one finding: place conflicting targets into predecessor /
   successor waves, validate and rerun tools after the predecessor, and only
   run independent targets with disjoint write scopes in the same wave.
1. Before launching a write-capable subagent, include a token-bounded handoff:
   the `Change Impact Packet` path, every target object in the repair batch,
   allowed files, and an object-by-object repair intent.
   For each target object, the parent must state the current problem, the
   intended structural change, why the behavior should remain unchanged,
   non-goals, and the validation that should prove the slice. Also include the
   forbidden semantic delta, tests to run, and required final format limited to
   changed paths, validation commands, and unresolved blockers. If the subagent
   returns broad prose, unrelated edits, or a file-level implementation without
   target-object trace, classify it as `handoff_prompt_gap`, repair this prompt,
   and do not launch the next writer until the handoff is narrowed.
1. Keep runtime metrics collection active for every write-capable subagent.
   The active run bundle must be discoverable through
   `AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR` or `reports/agents/.active_run`
   before spawning. After each write-capable subagent result, record one
   `workflow_monitor.py --behavior-event` line with
   `subagent_output_revision=none|parent_revised|review_revised`, the
   `subagent_target` or `subagent_agent_type`, the `repair_batch_id`, the
   revision reason, and whether a follow-up tool rerun was needed. This is the
   source of truth for revision latency and handoff-quality analysis; do not
   rely on chat-only memory.
1. Treat an implementation handoff that fixes only one mechanically safe
   finding as a default smell, not the default plan. If a wave contains one
   target only, record the reason as root-contract risk, semantic risk,
   write-scope conflict, or validation isolation. If no such reason exists,
   classify the narrow handoff as `handoff_prompt_gap`, batch the related
   targets, and repair this skill/handoff before launching the next writer.
1. Run `test_designer` before implementation and keep regression coverage in the same pass.
1. If file structure changes, plan the integration check with `python3 tools/ci/check_merge_structure.py ...`.
