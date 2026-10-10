# pr-processing

<!--
@dependency-start
contract skill
responsibility Processes authorized Issue and PR operations, using queue planning only for interacting candidates.
upstream design ../canonical/skills.md public Skill registry
upstream design ./agent-orchestration.execution-contract.toml conditional coordination policy
upstream design ../internal-routines/github-connected-work.md current-session GitHub transport and PR readback
upstream design ../internal-routines/github-status-lifecycle.md conditional Issue status changes
upstream design ../internal-routines/verification-result-structuring.md reader-reproducible publication
upstream design ./issue-finding-report.md Issue ownership and reorganization
upstream design ./agent-canon-update.md source PR and parent-pin route
upstream design ../../documents/conventions/coding-conventions-testing.md bug reproduction evidence
upstream implementation ../../tools/repository/git/conflict_preservation.py conflict inventory and readback
upstream implementation ../../tools/repository/github/github_publish.py authorized GitHub publication
downstream design ../../.codex/personal/skills/pr-processing/SKILL.md runtime discovery adapter
@dependency-end
-->

## Purpose

Process an authorized GitHub Issue or PR operation from current target state
through publication readback. One independent candidate uses the fast path;
queue-wide planning is conditional on actual dependencies or collisions.

## Work from the current connected session

For GitHub work from the current connected session, use
[github-connected-work](../internal-routines/github-connected-work.md). It owns
transport adaptation; this Skill retains the requested operation, target,
authority, and readback.

## Single-candidate fast path

For one independent PR, read its current base and head, diff, selected
validation and review state, required checks, and write authority. Do not
inventory unrelated PRs or require queue closure.

## Dependency queue path

Build a candidate graph only when source-to-pin order, shared files, conflicts,
base chains, or publication order constrain the next action. Refresh candidates
whose base or head becomes stale after earlier work. Apply the
[work-conservation contract](agent-orchestration.md#execution-time-aware-work-conservation-contract)
only to this selected coordination.

## Validation and repair

The changed surface owns repair. Run or wait for checks only when the changed
contract or requested operation requires them. An unrelated pending or failed
check does not block an independent publication or authorize cancellation or
rerun; required branch protection checks still block merge. Report unavailable
or unrun required validation honestly.

A bug handoff uses the existing
[reproduction-evidence owner](../../documents/conventions/coding-conventions-testing.md#22-bug-reproduction-evidence);
this does not require adding a test.

A hosted check is executor_unavailable only for the exact PR head when no
repository-owned step ran and the runner was not assigned with an external
service annotation. Any
repository-owned step failure remains a branch-owned failure. Local validation
is separate evidence, not a green hosted status.

## Base integration and merge readiness

Creating or updating a PR and handing it to review do not authorize a merge. For
an authorized merge, use [github-connected-work](../internal-routines/github-connected-work.md)
and the [conflict-preservation owner](../../documents/tools/repository_topic_clone.md#競合の再開):
integrate the current base on the PR branch, resolve each conflict against its
source owner, preserve unrelated and unknown user content, validate the
integrated head, and confirm the remote head still matches it before merging.
Merge against that expected head and read back the merge commit, tree, and
updated base.

A conflict-free path list alone does not prove semantic preservation. Do not
replace whole files or discard unknown state to make a merge pass; use the
preservation inventory and readback. If any required check, review, thread
resolution, or head/base fact is unproven, do not claim merge readiness. The
preservation tool and connected-work route own the detailed packet and operation
sequence.

## Publication boundary

Before any Issue or PR write, keep the requested operation,
repository-qualified target, authority, and real payload aligned through
dispatch and readback. Do not probe write access, create a substitute Issue after
a failed update, or blindly repeat an ambiguous create. Use the existing
publication route. Before an explicitly authorized new Issue, use
[issue-finding-report](issue-finding-report.md) to resolve ownership and
duplicates. For Issue or PR bodies and comments, use the existing
[reader-result structuring owner](../internal-routines/verification-result-structuring.md).

## Repository-qualified Issue identity

Identify Issues as owner/repository#number, resolved from fresh remote state.
Keep consumer and upstream Issues distinct in cross-repository work, and read
back the same qualified identity after a write.

## GitHub Issue status lifecycle delegation

Use the private
[github-status-lifecycle](../internal-routines/github-status-lifecycle.md)
route only when an explicit request or repository policy calls for status-label
mutation. This Skill resolves the target and supplies current work and
validation facts; the lifecycle owner applies and verifies the status change.

## Completion

Issue updates and PR creation/update or review handoff complete at the requested
scope after publication readback. Merge completion also requires the selected
checks, reviews, conflict preservation, expected-head merge, and post-merge
readback. A PR existing does not complete unfinished in-scope work.
