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

1. Resolve the current request and the relevant existing implementation or abstraction. For a split/extraction or a suspected missing predecessor, consult the relevant history and prior design when needed to decide reuse; do not add this search to every small edit.
2. Keep the selected capability, actual gap, and adoption/rejection rationale in the existing context or referenced record. Reuse that evidence rather than enumerating all candidates in a fixed grammar.
3. Build `direct_luna_handoff_packet_v1` with `tools/agent/orchestration/direct_luna_dispatch.py`. `workspace-write` still requires explicit bounded `allowed_paths`; invalid authority, escaping paths, and overlap with `do_not_read` remain errors. Context cannot enlarge these permissions. Do not read or assign writes to an asset outside the authorized boundary merely because it appears in the evidence.
4. For a necessary launch under [Context-preserving continuation](#context-preserving-continuation), spawn direct `gpt-5.6-luna` with `fork_turns="none"` and the serialized packet. The same context and source references reach the worker/reviewer without an independently reconstructed survey.
5. Read back the effective child model and reasoning effort before admitting work.
6. If the override is rejected or unavailable, return `direct_luna_unavailable`.
7. If effective metadata is hidden or differs from the request, return `direct_luna_unverified`.
8. Never substitute Sol, Terra, Spark, or a legacy role alias after either blocker.
9. Accept only the packet's expected output, evidence, blockers, and validation observations as the handback.
10. Continue with the same active verified child, sending only the changed objective, findings, or scope within its authority. Use the continuation rules below when reuse is not possible. Do not use unverified native resume.

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

## Complexity invariant

Let `P` be the physical execution-profile set and `R_active` the active logical-role instances. Static runtime configuration is `O(|P|)` and communication is `O(|R_active|)`. Adding a logical role that reuses an existing Luna profile must not add another physical team member.

A complete map from candidates to fixed disposition labels does not establish that their capabilities satisfy the request. Removing that duplicate representation keeps the actual reasoning in its existing owner and leaves permissions to the explicit authority fields.

Model identity does not preserve context: fresh reviewer and writer instances each
reconstruct their needed context, while compatible continuation reuses it and needs
only the delta. This is the engineering basis, not a measured token-saving claim.

## Output

Return matching `direct_luna_runtime_evidence_v1` plus the expected child output, or one typed blocker: `direct_luna_unavailable` or `direct_luna_unverified`.
