# Source Publication to Parent Projection Handoff

## Purpose

This contract closes the source-publication to parent-projection boundary for a repository that still owns a live `vendor/agent-canon` gitlink. It does not relax the parent gate and does not authorize a manual gitlink fast-forward.

The cross-namespace handoff has exactly one payload: the validated `agent-canon.source-projection-packet.v1` record. QueueReceipt, DependencyFrontier, transaction marker, and G4 are derived in the parent owner namespace by the canonical `tools/update_agent_canon.sh` front door. They are never copied from a source checkout or another parent.

## Owner equation

Let

- $S$ be the AgentCanon source checkout that owns source PR publication readback;
- $P$ be the parent repository whose gitlink and root projection will advance;
- $L(P)=P/.agent-canon/update-lifecycle$ be the lifecycle owner namespace.

All mutable lifecycle outputs satisfy

$$
\operatorname{owner}(\text{packet, queue, frontier, marker, G4}) = L(P),
$$

independently of the physical location of $S$. The source checkout supplies validated code and remote-main readback; it does not own the parent records. Binding the namespace to $S$ makes a managed source clone incapable of repairing an older parent pin and creates the bootstrap deadlock fixed by issue #724.

## Source publication producer

After authoritative source PR merge/readback, the publication owner assembles the exact predecessor records:

- RecordBinding;
- SourceMainRebindReceipt;
- CandidateCasReceipt;
- merged PullRequestLifecycle;
- PublicationReadbackReceipt;
- ordered G1, G2, and G3 verdicts;
- ordered predecessor evidence `#388 -> #389`;
- frontier acceptance evidence reference.

The producer invokes the sole packet materializer and parent handoff owner:

```bash
python3 tools/agent_tools/source_projection_handoff.py publish \
  --root "${AGENT_CANON_PARENT_ROOT}" \
  --input "${SOURCE_PROJECTION_COMPONENTS_JSON}"
```

`--input` is either the complete validated source-projection packet or an object containing exactly the eight predecessor fields accepted by `materialize_source_projection_packet`. First publication uses the parent boundary's atomic no-replace primitive, so concurrent publishers cannot replace the winning packet. Existing output is accepted only when immutable replay validation proves semantic identity equality, and its original bytes are preserved. A different packet at the same parent path is a typed failure and is not overwritten.

## Canonical advancement

A current source checkout can repair a parent that is still pinned to an older AgentCanon commit. Execute the current source front door with an explicit parent-root handoff; do not stage the parent gitlink first:

```bash
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON="publish accepted AgentCanon lifecycle evidence to the parent owner" \
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:<sha256-of-exact-authorization-evidence-bytes>" \
AGENT_CANON_SOURCE_PROJECTION_HANDOFF="${SOURCE_PROJECTION_PACKET}" \
python3 "${AGENT_CANON_SOURCE_ROOT}/tools/agent_tools/parent_root_side_effects.py" \
  exec-parent-bound \
  --root "${AGENT_CANON_PARENT_ROOT}" \
  --source-root "${AGENT_CANON_SOURCE_ROOT}" \
  --purpose agent-canon-update-script \
  --issue-handoff \
  -- bash "${AGENT_CANON_SOURCE_ROOT}/tools/update_agent_canon.sh" latest
```

The source front door validates publication commit/tree against remote `main`, writes or replays the packet in $L(P)$, and derives QueueReceipt, pending/accepted DependencyFrontier, current transaction marker, and G4 directly in $L(P)$. The parent updater can then run `apply` and validate those records before changing the gitlink/root projection.

A parent already running a version that contains this contract may consume the same packet directly during `latest` or `apply`. This is one front door and one record model, not a compatibility updater.

## Failure semantics

The route fails before parent projection when any of the following holds:

- packet publication commit/tree differs from authoritative remote `main` readback;
- packet predecessor, binding, G1-G3 order, or immutable identity is invalid;
- a parent-owned packet or derived receipt exists with a different identity;
- a packet target is a symlink, leaves the authenticated parent root, or changes identity during publication/readback;
- no accepted derived lifecycle exists and no source-publication packet handoff is available;
- the proposed parent output is outside the attested parent root.

The missing-handoff diagnostic names `source_publication_handoff_missing`. It must not recommend receipt fabrication, receipt copying, root-view overwrite, or manual mode-`160000` gitlink staging.

## Acceptance

Fresh-clone acceptance begins with an empty parent lifecycle namespace, places only the source-projection packet in $L(P)$, invokes the source front door against $P$, and verifies that the four derived artifacts appear in $L(P)$. Copying derived artifacts from a standalone fixture is prohibited because it bypasses the production boundary being tested.

A second invocation with the same packet must preserve packet and derived-record identity. Changed source publication identity requires a successor transaction rather than mutation of the accepted transaction.
