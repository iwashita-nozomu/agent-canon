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

Run the repository's existing entrypoint with its configured environment.
Use the dependencies' diagnostics and exit statuses. A separate check is useful
when it covers a condition the installed environment can encounter and the
dependency leaves that condition unchecked. Keep access and resource boundaries
with the execution entrypoint.

Follow an observed failure to the responsible code or configuration. If the first
route cannot complete the request, try an existing route that preserves the
required behavior and validation. Continue independent work while investigating.
Report the evidence and its effect on the requested outcome.

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
For AgentCanon topic checkouts, read [repository-topic-clone](../skills/repository-topic-clone.md)
at cleanup; checkout drift is owned by [worktree-health](../skills/worktree-health.md).

## Branch and storage owners

Before an AgentCanon branch operation, read [Branch Scope](../../documents/operations/BRANCH_SCOPE.md)
and the selected [branch reuse/authority section](CODEX_INTAKE.md#branch-reuse-default).
Before an annex pointer or payload operation, read [annex](../../documents/operations/annex.md).
Keep branch metadata and payload ownership distinct; these source-specific links do
not add AgentCanon paths to a generated consumer's portable rules.

## Team ownership

Before forming, changing, or delegating an AgentCanon team, read the selected
[orchestration decision](../skills/agent-orchestration.md#decision-order), then its
selected row in `agents/task_catalog.yaml` and the applicable
[subagent procedure](CODEX_SUBAGENTS.md). The typed route owns logical roles,
model/profile, Skills, authority, and handoff. Candidate lists do not activate
instances; logical-role coverage is not an instance count. Retain the common
root's parent-executed user-guided debugging boundary. Consumer teams continue to
use their own self-contained guidance.
