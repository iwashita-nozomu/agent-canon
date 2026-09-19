# Execution boundaries

<!--
@dependency-start
contract agent-runtime
responsibility Owns detailed source-side environment, checkout, cleanup, and team boundaries.
upstream design ../../AGENTS.md conditional source reader map
upstream design ../../ROOT_AGENTS.md portable common boundaries
upstream design ../../documents/design/entrypoint-owner-map.md source and consumer split contract
@dependency-end
-->

Read the section selected by the source [AGENTS.md](../../AGENTS.md) Reader Map
when its responsibility is active. This is source-side detail, not an
additional startup packet or a dependency of generated consumer instructions.

## Configured execution and bounded diagnosis

Run the current repository owner's existing entrypoint with its configured
settings and standard tool defaults. This owner-defined procedure is the fixed
execution route: entrypoint, configuration resolution, required backend,
formatter, validation, and publication steps. Task inputs may vary through its
documented parameters; fixed does not mean frozen argv, absolute paths, versions,
or SHAs. Preserve native resolution and existing integrity/pin requirements.

Carry the selected route through retries, resumption, and delegation. Reuse its
owner reference and known command in the existing task/Issue or handoff; a callee
consumes that selection rather than rerouting. Do not add a route manifest, lock,
extra approval, or per-command proof to establish continuity.

An entrypoint failure is not permission to call a lower-level implementation,
recreate the steps in a temporary script or GitHub Actions workflow, add a wrapper,
or substitute another backend, runtime, daemon, worker, or formatter. Use a direct
native command or alternate transport only when the existing owner already defines
it for that operation and its conditions hold; discovery or success alone does
not authorize an alternative or establish equivalent validation.

Use the actual failed command/result to locate and repair the cause at its owner
first; follow directly related consumers for demonstrated in-scope defects, not
unrelated cleanup. Retry through the same entrypoint only when reruns are allowed.
If the route itself must change, update its owning configuration, implementation,
and instructions as applicable within the authorized scope and existing Issue/PR
workflow. Record the reason and validate the changed contract before claiming
success. A failure or available tool is not authority to change the route.

The engineering reason is that bypassing the entrypoint can drop its configuration,
permissions, resource limits, or failure semantics. Success on that bypass does
not prove the selected route; repairing its owner avoids a second implementation.

Manual environment selection for ordinary
execution is prohibited: do not ask the user to choose an environment or inject
host/container, OS/WSL, CPU/GPU backend, runtime, or profile selectors through
ad-hoc command flags, environment variables, or configuration edits. Existing
tools resolve their own configured settings and defaults; missing optional
selectors are not inputs to solicit or fill.
Do not insert environment classification, inventory, or rediscovery before
ordinary tasks, sessions, or commands, including installed-tool probes. Reuse
supplied, still-applicable context without repeating probes or confirmation.
A new task or an unknown optional setting is not a reason to investigate, stop,
reconfigure, or restart a working route. Do not replace manual selection with
new auto-detection, flags, profiles, environment variables, fallbacks, wrappers,
or persistent detection/cache state. Do not invent missing settings merely to
normalize environments or avoid rediscovery.
Environment diagnosis is limited to an explicit request, an actual relevant
failure, an observed change to a required premise, or a concrete evidenced
risk. Resolve only the missing decision-relevant fact and stop the diagnosis
when it is resolved; diagnosis alone does not authorize setup or repair.
Environment changes and their rebuild/full-profile acceptance must belong to
the authorized task, not become prerequisites for ordinary execution.
Preserve the selected command's required safety checks, permissions, resource
limits, and rerun prohibitions; prior success does not override contrary
current evidence. When blocked, identify the concrete prerequisite or risk and
its evidence, stop only affected commands, and continue independent authorized
work. Do not silently switch a required backend, weaken validation, or treat
an unrun command as passed.

## Checkout and dependency identity

Establish the actual working directory and Git root, branch, and `HEAD`, then
trace the selected owner's dependency and consumer edges. At each existing branch/checkout readback
boundary, include the actual clones under the task's `workspace/<...>`, not
only the parent checkout or its declared pins. For each in-scope dependency,
inspect its resolved path, repository identity, branch or detached state,
actual `HEAD`, dirty state, and declared pin against the source actually read
by the selected build/import/execution route. A dependency development clone
and the consumer's pinned checkout are distinct observations; a named path is
only a candidate until that trace confirms the responsible replaceable unit.
Record no dependency only after the trace shows that no edge applies, never
from an unperformed inspection. Re-read the affected identity and dependency
state after a directory, branch, dependency checkout, PR revision, pin, or
source-resolution change; unchanged ordinary commands do not require duplicate
readback. If the consumer's existing dependency contract requires an exact pin,
execution that needs a dependency change uses a published PR commit through
that consumer-owned pin before it runs. Otherwise use the consumer's declared
resolution and record the actual input; do not introduce a pin or a SHA check
to follow this workflow. Dependency-local development validation remains
separate from consumer validation, and an unpinned run must not be reported as
pinned-input verification. Preserve mismatched or unknown checkouts and do not
treat their unverified input as the declared pin. This does not introduce an
AgentCanon dependency into a source-free consumer.

## Temporary checkout cleanup

When a task-owned temporary clone is no longer needed, use the applicable
repository cleanup owner immediately rather than waiting for task or PR closeout.
First establish that no active work depends on it and no unpreserved local state
would be lost; unknown or user-owned clones remain untouched. Record removal
or the specific retention reason in the existing task result. This is checkout
cleanup, not authorization to delete remote branches or a shared workspace.

## Branch and storage owners

Before a branch or annex operation, read the applicable repository's branch and
storage owners. Keep Git branch metadata and any annex payload as separate
concerns, and let those owners authorize data operations. This common base
defines the read edge only; it does not name a source-repository path or
prescribe an annex command, so a generated consumer root remains self-contained.

## Team ownership

Before forming, changing, or delegating a team, read the applicable repository
team owner and the selected orchestration skill, then follow the selected typed
route's definitions for logical role, model/profile, skills, authority, and
handoff. Candidate role lists are not activation instructions, and logical-role
coverage is not a physical-instance count. Keep consumer-owned team guidance
self-contained; a source-specific checkout may name its canonical AgentCanon
team owners, but a consumer root must not import or copy those source paths.
