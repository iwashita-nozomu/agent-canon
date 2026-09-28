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

For a program execution request, use this order:

1. Invoke the repository owner's prescribed entrypoint with its existing settings
   and standard defaults. Reuse known roots, selectors, and context; do not run
   separate `status`, identity, installed-tool, backend, or availability probes
   before the requested command.
2. If it succeeds, continue the task without route diagnosis. If it fails, keep
   the exact command, output, exit/signal, and execution plane. An entrypoint
   rejection is failure evidence even when the program did not start; do not
   replay it merely to obtain another failure record. Shared cwd, hostname, or
   checkout does not prove parent/worker execution equivalence. Keep a worker's
   access failure scoped to that worker, not a host outage or test assertion.
   Preserve observed parent success as counterevidence, not proof of worker repair.
3. Use that failure to inspect only the route facts needed to locate the problem.
   A program assertion or test failure is not by itself an environment defect.
   When isolation is implicated, compare relevant effective sandbox/approval,
   groups/namespaces, and socket visibility/access without dumping credentials.
   Trace the effective setting through the actual runtime version, launch, and
   loaded configuration to its concrete owner; generated defaults alone do not
   prove which override ran. Repair confirmed causes and affected generated
   consumers at that owner, not through parent-only test substitution or weakened
   permissions. Reuse existing evidence; this is not a startup probe checklist.
   Stop diagnosis when the relevant decision is resolved; repair and any retry
   still require the existing scope, authority, and rerun allowance.

Do not ask the user to select an environment or inject ad-hoc host/container,
OS/WSL, CPU/GPU, runtime, or profile overrides. Missing optional selectors and
new tasks/sessions do not justify discovery, setup, wrappers, auto-detection,
cache state, or fallback execution. Successful execution does not prove every
validation property, but an additional route probe does not prove it either.

Keep required safety, permission, target-admission, integrity, and resource checks
inside the selected entrypoint. This order does not bypass a known unsafe or
unauthorized operation. Explicit diagnosis, installation, or environment-change
requests use their own existing owner route; do not turn those procedures into
ordinary execution prerequisites. When blocked, preserve the concrete failure,
stop only affected commands, and continue independent authorized work. Never
switch a required backend, weaken validation, or report an unrun command as passed.

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
