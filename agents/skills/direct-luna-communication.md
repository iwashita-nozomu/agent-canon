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

Exchange one bounded packet between the parent and a direct Luna subagent without sharing implicit raw history or creating a physical custom-agent alias per logical role.

This Skill owns packet construction, runtime acknowledgement, and handback semantics. It does not choose the logical role, replace specialist Skills, grant authority, or provide a fallback model.

The validator checks the direct-Luna authority and runtime boundary. It does not prove the quality or completeness of a reuse investigation from a record's format, and it does not introduce admission requirements for other runtime routes.

## Inputs

The parent supplies `logical_role_id`, one or more existing `skill_ids`, `reasoning_effort`, `authority`, bounded `allowed_paths` and `do_not_read`, `expected_output`, the parent-owned `validation_route`, bounded `objective` and `context`, and applicable `request_clause_ids`.

Use the existing `context` to carry the relevant source, design, or Issue references and the actual reuse decision: which existing capability fits, what gap remains, and why the selected change is necessary. Worker and reviewer use the same evidence. Do not transcribe it into a second `reuse_survey` schema or require a fixed disposition vocabulary, non-empty `test_paths`, every historical evidence dimension, or a `not_applicable` token.

A bounded edit needs the evidence relevant to that edit, not an exhaustive asset inventory. A real missing design or reuse decision is resolved with its owning source; a non-empty field alone is not proof that investigation happened. References are context, never read or write authorization.

## Procedure

When a direct Luna child is selected, reuse the current request, source context,
and actual reuse decision. Investigate history or prior design only when a split,
extraction, or suspected missing predecessor makes it relevant. Keep the selected
capability and remaining gap in the existing context rather than building a
second inventory.

Build `direct_luna_handoff_packet_v1` with
`tools/agent/orchestration/direct_luna_dispatch.py`. For `workspace-write`, the
packet must carry explicit bounded `allowed_paths`; reject invalid authority,
escaping paths, and overlap with `do_not_read`. Context cannot enlarge those
permissions. If launch is needed, send the serialized packet to direct
`gpt-6-luna` with `fork_turns="none"`, then read back the effective model and
reasoning effort before admitting work. Return `direct_luna_unavailable` when
the override is rejected or unavailable, and `direct_luna_unverified` when
effective metadata is hidden or differs from the request. Do not substitute
another model or a legacy role alias after either blocker.

Use the packet's expected output, evidence, blockers, and validation observations
as the handback. Continue with a compatible active child by sending only the
changed objective, findings, or scope within its authority. A new child is for
initial work, a child that actually ended or was lost, or independent review;
unverified native resume is not a continuation route.

## Context-preserving continuation

Reuse a compatible active worker through implementation and repair. Stage changes,
packet names, or prompt shortening do not justify closing it and reloading context.
Use existing source/design references and send only the relevant delta.

An unavailable fixed worker is a blocker, not a reason to spawn a read-only Luna
reviewer and then a new Luna writer, even with explicit identical model selection.
Preserve the candidate and packet, report the blocked scope, and continue unaffected
authorized work without parent implementation or model substitution.

Start a fresh child only for an already selected responsibility that cannot reuse
an existing compatible child: initial work, an actually ended/lost child, or required
independent review. An unchanged authorization, model, or runtime blocker is not
cleared by a new role or packet. When review is independently required, keep it
separate from the author and reuse the reviewer for focused rechecks; return fixes
to the same active authorized writer, not a newly spawned writer by default.

## Authority invariants

Luna identity never grants write access. Read-only responsibilities remain read-only. `workspace-write` requires parent-assigned repository-relative paths and no overlap with `do_not_read`. An evidence reference or reuse decision never expands `allowed_paths` or permits a forbidden read. PR creation, merge, close, base integration, and administrative overrides remain parent-owned.

## Profile reuse

Logical roles reuse the configured Luna execution profile. Adding a role does
not create a physical alias or expand team capacity. A list of candidate labels
does not prove that a capability fits the request; use the selected role and
actual gap, with permissions remaining in the explicit authority fields.

Model identity does not preserve context: fresh reviewer and writer instances each
reconstruct their needed context, while compatible continuation reuses it and needs
only the delta. This is the engineering basis, not a measured token-saving claim.

## Output

Return matching `direct_luna_runtime_evidence_v1` plus the expected child output, or one typed blocker: `direct_luna_unavailable` or `direct_luna_unverified`.
