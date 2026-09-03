# Direct Luna Communication
<!--
@dependency-start
contract skill
responsibility Owns bounded packet exchange and effective-runtime acknowledgement for direct Luna subagents.
upstream design ./agent-orchestration.md selects the logical role, Skill set, execution profile, and authority.
upstream design ./subagent-bootstrap.md owns launch readiness and lifecycle handoff.
upstream design ../canonical/CODEX_SUBAGENTS.md owns capacity and logical-role lifecycle policy.
downstream implementation ../../tools/agent/orchestration/direct_luna_dispatch.py validates packets and runtime evidence.
downstream implementation ../../tests/tools/test_direct_luna_dispatch.py validates packet and readback invariants.
downstream implementation ../../tests/tools/test_direct_luna_topology.py validates profile-level topology.
@dependency-end
-->

## Purpose

Exchange one bounded, typed packet between the parent and a direct Luna subagent without sharing implicit raw history or creating a physical custom-agent alias per logical role.

This Skill owns packet construction, runtime acknowledgement, and handback semantics. It does not choose the logical role, replace specialist Skills, grant authority, or provide a fallback model.

## Inputs

The parent supplies `logical_role_id`, one or more existing `skill_ids`, `reasoning_effort`, `authority`, bounded `allowed_paths` and `do_not_read`, `expected_output`, the parent-owned `validation_route`, bounded `objective` and `context`, and applicable `request_clause_ids`.

A `workspace-write` packet also supplies one structured `reuse_survey`. The same survey may be supplied unchanged to a read-only worker/reviewer successor. An applicable survey records one decision per discovered candidate with `asset_path`, `asset_origin`, `capability`, `disposition` (`reuse|extend|restore|consolidate|replace|delete|reject`), `reason`, and non-empty `test_paths`. It also records the current-asset, Git-history/deleted-path, prior PR/Issue, and predecessor/design evidence needed by the selected `current` or `current_and_history` scope. An evidence dimension that is genuinely inapplicable is carried as a categorized `bounded_omission`; it is not silently absent.

A bounded non-split edit with no reuse choice may use `scope=not_applicable`, but only with an explicit reason and no synthetic asset evidence. This is the only write-capable path that does not carry candidate decisions.

## Procedure

1. Before any file or worker slice, construct the single current asset universe. For code split/extraction or a missing suspected predecessor, extend that same universe with Git history/deleted paths, prior PR/Issues, predecessor tests, and relevant design documents.
2. Assign every discovered candidate exactly one supported disposition and bind the reason and test paths. A proposed new surface is admissible only when every candidate in the completed/bounded universe is explicitly `reject` with evidence.
3. Build `direct_luna_handoff_packet_v1` with `tools/agent/orchestration/direct_luna_dispatch.py`. `workspace-write` fails closed on a missing/incomplete survey, duplicate candidate path, missing evidence dimension, write disposition outside `allowed_paths`, or asset/test path that crosses `do_not_read`.
4. Spawn direct `gpt-5.6-luna` with `fork_turns="none"` and the serialized packet. The serialized `reuse_survey` is the worker/reviewer prompt evidence; do not restate or independently reconstruct it.
5. Read back the effective child model and reasoning effort before admitting work.
6. If the override is rejected or unavailable, return `direct_luna_unavailable`.
7. If effective metadata is hidden or differs from the request, return `direct_luna_unverified`.
8. Never substitute Sol, Terra, Spark, or a legacy role alias after either blocker.
9. Accept only the packet's expected output, evidence, blockers, and validation observations as the handback.
10. Continue by updating the same active verified child, or start a fresh Luna child with another bounded packet. Do not use unverified native resume.

## Authority invariants

Luna identity never grants write access. Read-only responsibilities remain read-only. `workspace-write` requires parent-assigned repository-relative paths, a valid structured `reuse_survey`, and no overlap with `do_not_read`. A rejected foreign candidate remains evidence only and never expands `allowed_paths`. PR creation, merge, close, base integration, and administrative overrides remain parent-owned.

## Complexity invariant

Let `P` be the physical execution-profile set and `R_active` the active logical-role instances. Static runtime configuration is `O(|P|)` and communication is `O(|R_active|)`. Adding a logical role that reuses an existing Luna profile must not add another physical team member.

For an applicable survey, let `A` be the finite discovered asset set and `D` the seven supported dispositions. Admission requires a total single-valued map `d: A -> D`; duplicate paths, unclassified candidates, or missing evidence make the map undefined and therefore block the write packet. Worker and reviewer packets serialize the same `reuse_survey`, so prompt projection adds no second decision state.

## Output

Return matching `direct_luna_runtime_evidence_v1` plus the expected child output, or one typed blocker: `direct_luna_unavailable` or `direct_luna_unverified`.
