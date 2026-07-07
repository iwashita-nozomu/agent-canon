---
name: refactor-loop
description: Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates.
---
<!--
@dependency-start
contract skill
responsibility Documents Refactor Loop for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable refactor structure contracts
upstream design ../../../agents/skills/dependency-analysis.md defines change-impact and repair-planning packets
upstream design ../../../agents/skills/tool-finding-report.md tool-based finding packet workflow
upstream implementation ../../../tools/agent_tools/check_design_doc_claims.py emits design evidence findings for refactor plans
@dependency-end
-->


# Refactor Loop

## Reader Map

- Purpose: expose the behavior-preserving refactor loop to Codex skill
  discovery and enforce dependency-expanded refactor planning.
- Section path: Tool Commands gives the command packet; the numbered rules hold
  dependency analysis, orchestration planning, structural deltas, API migration,
  finding-packet feedback, and review routing.
- Use when: large refactors need path mapping, semantic-delta controls, repair
  batches, and strong review gates.
- Boundary: this shim points to `agents/skills/refactor-loop.md` for the
  canonical human-facing contract and does not authorize feature additions.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill refactor-loop --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Start from the dependency-expanded scope, not from the initially mentioned
   file. The editable candidate set is every file returned by dependency
   analysis for the requested object/file, plus validation commands and the
   tests/docs that own observable behavior or reader-facing contracts. Narrow
   implementation only after mapping target traces inside that expanded scope.
   A target trace is `path:start-end:qualname` for an existing function, method,
   or class, or `path:start-end:region-id` for a cohesive source region,
   behavior unit, or responsibility unit.
1. Use `$dependency-analysis` to create a structured `Change Impact Packet`
   manifest before choosing targets, writing the refactor orchestration plan,
   or launching a write-capable subagent. The packet is the unified
   repair-planning input; raw findings, raw search hits, and single filenames
   are not enough. Full dependency artifacts stay on disk and are read only for
   the current repair batch or disputed edges.
   Include `check_design_doc_claims.py` output when a design document provides
   the refactor rationale, so implementation-backed claims and parent-doc
   alignment enter the same repair packet.
1. Before launching implementation subagents, the parent must write a refactor
   orchestration plan from that dependency graph. Separate sequential root
   slices that must be fixed first from independent downstream slices that can
   run in parallel, assign each target trace to an owner/wave, and record
   `blocked_by`, allowed files, validation, and whether the slice is single-agent
   or parallel-safe.
   `$structure-refactor` owns structure surface classification, root/scope
   contract, path mapping, and runtime boundary; this skill owns repair batch
   sizing, `blocked_by`, sequential / parallel wave choice, and write-capable
   subagent orchestration.
1. Choose repair scope granularity from tool-generated `scope_candidates`, not
   from a fixed file/function rule. Optimize for the fewest coherent writer
   waves and tool reruns while preserving behavior contract clarity, write-scope
   isolation, token budget, validation surface, and semantic-risk boundaries.
1. The default implementation handoff is a dependency-expanded repair batch,
   not a single finding. Group every mechanically safe target in the same
   responsibility group, dependency wave, and validation surface into one
   target-by-target handoff. A single-finding handoff is allowed only after
   dependency evidence rejects a behavior-preserving canonical home, nearest
   valid ancestor, and batchable downstream repair; then record the isolation
   reason as root/shared contract risk, risky semantic change, or no batchable
   target. Record `review_required` / `deferred` only as that evidence-backed
   blocker.
1. Read `agents/skills/refactor-loop.md`.
1. Use `$structure-planning` before editing when file moves, module boundaries, repair slices, path mapping, responsibility maps, allowed structural delta, or forbidden semantic delta are nontrivial.
1. Fix `Behavior Contract`, `Allowed Structural Delta`, and `Forbidden Semantic Delta` before editing.
1. For API-shaping refactors, fix `Expected API` before editing and pass that
   expected API in every subagent handoff. Do not split the work merely to keep
   the repository runnable after each intermediate edit; per-step operation
   checks are not required until the user-facing return gate, where the final
   intended API and all updated call sites must be validated together.
1. Run API-shaping and structure refactors as a two-stage refactor:
   `forced migration` first, then `usage-surface repair`. The first stage
   moves or removes the canonical surface, legacy entry, alias, wrapper,
   config route, and generated surface as one structural migration. The second
   stage updates every caller, document, workflow, skill, hook, config, and
   report consumer that uses the moved surface. Put test, smoke, and behavior
   execution in return-gate validation after both stages are complete.
1. Explicitly list every target trace being changed before editing. Use
   `path:start-end:qualname` for actual functions, methods, and classes, or
   `path:start-end:region-id` for cohesive source regions, behavior units, and
   responsibility units. Do not start implementation from a file-level or
   module-level target alone. Do not split or extract code solely to create a
   qualname; a new boundary requires caller contract, state ownership, domain
   vocabulary, effect boundary, validated decision point, or stable reusable
   behavior.
1. If a shared policy or base abstraction is being consolidated, first declare the canonical module/object, refactor that root surface, then run dependency and usage scans before touching dependents.
1. Record delete, move, rename, and split targets before implementation.
1. Keep feature additions out of the same pass.
1. For dependency-guided structural duplicate cleanup, generate `priority_order`
   and `repair_slice` through `$tool-finding-report`, build
   dependency-expanded repair batches/waves, process one dependency-ordered
   wave at a time, and include related mechanically safe targets in the same
   batch when they share responsibility group and validation surface. Feed the
   finding packet into `$dependency-analysis` to join code/header/search impact,
   generate tool-made `impact_blocks`, expand downstream affected files, and
   classify `review_required`, `deferred`, or current-state/no-op outcomes as
   evidence-backed blockers only after dependency evidence rejects a
   behavior-preserving canonical home, nearest valid ancestor, and batchable
   downstream repair.
   For Python structural findings, the default planning command is
   `agent-canon python-structure-hash-scope-plan --input <report.json> --dependency-report-dir <dependency-review-dir> --output <change-impact-packet.json>`.
1. After each implementation slice, if a finding packet exists, join the latest
   `git diff` against it; otherwise join the diff against owner-selected static
   / targeted validation artifacts and target trace. Produce a
   `diff_linked_findings` artifact that separates direct changed-line findings,
   related structural findings for changed target traces and their dependency /
   representative instances, and unchanged out-of-slice findings.
1. Use `$tool-finding-report` and baseline capture proportionally: require them
   for behavior-changing or regression-prone code refactors, missing behavior
   oracles, root/shared contract waves, or tool-owned global properties. For
   prompt/doc/static-contract refactors, use owner-selected static and targeted
   validation. Repair `handoff_prompt_gap` or `shared_skill_or_workflow_gap`
   before the next writer only when the gap affects the selected next batch,
   review safety, or behavior-preservation evidence; otherwise record it as
   follow-up and continue with a corrected bounded handoff for unaffected
   targets.
1. If refactor validation fails, record `failing_contract`,
   `observation_level`, `cause_classification`, `intent_preservation`, and
   `evidence` before changing behavior-preserving intent, simplifying to
   pass, reverting, deleting intended behavior/tests, weakening an oracle, or
   downscoping validation. Preserve `Forbidden Semantic Delta` for
   implementation bugs and route oracle/spec, fixture/environment/stale
   artifact, unrelated, and approved-design/user-request conflicts into the
   next owner repair, residual, or escalation plan.
1. For non-trivial refactors, route implementation and review to separate
   subagents: parent fixes the contract and artifacts, one or more
   wave-scoped write-capable `worker`/`spark_worker` agents implement,
   `test_designer` defines regression coverage before behavior-changing or
   regression-prone code changes, and a
   separate read-only reviewer
   (`python_reviewer`, `cpp_reviewer`, or `reviewer`) reviews the latest diff
   with before/after scan, impact evidence, and `diff_linked_findings`.
   Low-level dependency/root slices run first with the fewest write-capable
   agents. Conflict risk must be resolved by task order, not by shrinking the
   repair batch to one finding: place conflicting targets into predecessor /
   successor waves, validate and rerun tools after the predecessor, and only
   run independent targets with disjoint write scopes in the same wave.
1. Before launching a write-capable subagent, include a token-bounded handoff:
   the `Change Impact Packet` path, every target trace in the repair batch,
   allowed files, and a target-by-target repair intent.
   For each target trace, the parent must state the current problem, the
   intended structural change, why the behavior should remain unchanged,
   non-goals, and the validation that should prove the slice. Also include the
   forbidden semantic delta, tests to run, and required final format limited to
   changed paths, validation commands, and unresolved blockers. If the subagent
   returns broad prose, unrelated edits, or a file-level implementation without
   target trace, classify it as `handoff_prompt_gap`, repair this prompt,
   and do not launch the next writer until the handoff is bounded by target
   traces.
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
   target only, first record dependency evidence rejecting a behavior-preserving
   canonical home, nearest valid ancestor, and batchable downstream repair; only
   then record the isolation reason as root-contract risk, semantic risk,
   write-scope conflict, or validation isolation. If no such evidence-backed
   reason exists, classify the underspecified handoff as `handoff_prompt_gap`,
   batch the related targets, and repair this skill/handoff before launching the
   next writer.
1. Run `test_designer` before behavior-changing or regression-prone implementation and keep regression coverage in the same pass. For contract-only wrapper refactors, use static contract validation and canonical command evidence.
1. If file structure changes, plan the integration check with `python3 tools/ci/check_merge_structure.py ...`.
