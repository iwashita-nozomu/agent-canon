# Direct Luna Communication

## Purpose

Exchange one bounded, typed packet between the parent and a direct Luna subagent without sharing implicit raw history or creating a physical custom-agent alias per logical role.

This Skill owns packet construction, runtime acknowledgement, and handback semantics. It does not choose the logical role, replace specialist Skills, grant authority, or provide a fallback model.

## Inputs

The parent supplies `logical_role_id`, one or more existing `skill_ids`, `reasoning_effort`, `authority`, bounded `allowed_paths` and `do_not_read`, `expected_output`, the parent-owned `validation_route`, bounded `objective` and `context`, and applicable `request_clause_ids`.

## Procedure

1. Build `direct_luna_handoff_packet_v1` with `tools/agent_tools/direct_luna_dispatch.py`.
2. Spawn direct `gpt-5.6-luna` with `fork_turns="none"` and the serialized packet. Do not pass unselected conversation history.
3. Read back the effective child model and reasoning effort before admitting work.
4. If the override is rejected or unavailable, return `direct_luna_unavailable`.
5. If effective metadata is hidden or differs from the request, return `direct_luna_unverified`.
6. Never substitute Sol, Terra, Spark, or a legacy role alias after either blocker.
7. Accept only the packet's expected output, evidence, blockers, and validation observations as the handback.
8. Continue by updating the same active verified child, or start a fresh Luna child with another bounded packet. Do not use unverified native resume.

## Authority invariants

Luna identity never grants write access. Read-only responsibilities remain read-only. `workspace-write` requires parent-assigned repository-relative paths and cannot overlap `do_not_read`. PR creation, merge, close, base integration, and administrative overrides remain parent-owned.

## Complexity invariant

Let `P` be the physical execution-profile set and `R_active` the active logical-role instances. Static runtime configuration is `O(|P|)` and communication is `O(|R_active|)`. Adding a logical role that reuses an existing Luna profile must not add another physical team member.

## Output

Return matching `direct_luna_runtime_evidence_v1` plus the expected child output, or one typed blocker: `direct_luna_unavailable` or `direct_luna_unverified`.
