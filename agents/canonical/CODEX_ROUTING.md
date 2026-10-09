# Codex Routing

<!--
@dependency-start
contract agent-runtime
responsibility Owns task classification, skill and profile selection, and Codex-specific routing.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
upstream design ../task_catalog.yaml typed family and execution-route selection
@dependency-end
-->

Read the named section only while its selection is unresolved. Return to
[Codex Workflow](CODEX_WORKFLOW.md#reader-map) after the decision; preserve it
until its premises change.

## Runtime Profile And Risk Selection

Use established structure, owner, and touched-contract evidence with the
[profile/check matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md).
The selected profile determines validation and checker obligations. It does not
limit context, work scope, team mode, or task size, and selecting it needs no
fresh environment preflight. Record the selection and evidence in the existing
task result; inactive profiles need no inventory.

Child handoff follows `agents/task_catalog.yaml#workflow_activation_policy`
and the selected typed route. Candidate roles do not activate themselves. When
an activated child is blocked, preserve its typed failure and the existing
authority boundary; use the selected execution owner rather than a parent
fallback. User-guided debugging retains the common ROOT boundary.

## Task Classification

Select the primary family from [the task catalog](../task_catalog.yaml), using
`tasks[].family` and `workflow_activation_policy`. The
[family reader paths](../TASK_WORKFLOWS.md#workflow-family-reader-paths) explain
those records, including Owner-Bounded Change and IssueWorker Publication.
Keep one selected primary family when work spans domains. This document does
not maintain another family enumeration or infer mandatory stages from size,
file type, or prompt keywords.

Environment work selects its family only when an environment/configuration
contract is actually in scope. Existing-environment execution or an unavailable
test does not initiate environment maintenance. The selected environment owner
keeps product validation separate from AgentCanon runtime validation.

Use `execution_route_policy` to distinguish `bounded_fast_path` and
`coordination`. Bounded work has one execution owner and uses existing task
evidence without requiring a child or run bundle; its internal work follows the
selected owner and actual dependencies. Coordination assigns its units and uses
its declared run bundle.

## Contract-Required Skill Set

Apply [agent orchestration](../skills/agent-orchestration.md#decision-order)
when workflow/Skill/role selection is unresolved; reuse a resolved selection.
Public identity, description, discovery path, and prompt triggers belong to
[the Skill catalog](../skills/catalog.yaml). Prerequisites and conditional
related candidates belong to [the dependency dictionary](../skills/skill-dependencies.yaml).
Read [Skill Paths](skills.md#skill-paths) only for an unresolved adapter or
command context, and read the selected Skill's active sections before use.

The existing `route` command uses `--mode routing-only` for read-only work
and `--mode repo-changing` for a selected repository/remote mutation. Reading
source for an answer or diagnosis does not widen the mode.
`codex-task-workflow` becomes active for execution transport; `subagent-bootstrap`
becomes active only when the selected typed route requires child handoff.
User invocation uses `$skill-name`.

A later operation, finding, or changed premise can activate a related Skill.
Select it under the caller's stated condition, read its current sections, and
regenerate its command packet before a selected handoff. Required commands,
task-matching conditional commands, and selected validation retain their order.
Catalog command argv are logical tool routes, interpreted through the existing
[CLI owner](CLI_ENTRYPOINTS.md#tool-commands), not Host execution recipes.

Before claiming a capability gap in an API, dependency, configuration, or
extension point, use [API surface traversal](../../documents/design/api-surface-traversal-policy.md).
Check public imports/exports, signatures, nested configuration, examples, and
actual consumers; retain the source-backed decision in the owning design.

Public failure recording uses [Notes Lifecycle](../../documents/operations/notes-lifecycle.md#failed-verification-record).
Select [agent-learning](../skills/agent-learning.md#reader-map) for private
knowledge/feedback or an agent-behavior learning decision. Stable preferences
are explicit changes to their canonical owner.

## 2. Workflow Selection

Use the selected family record and [workflow reader paths](../TASK_WORKFLOWS.md#workflow-family-reader-paths).
Select only stages and review claims required by that route. Existing resolved
owner and validation facts remain valid across the transition.

## 3. Placement

When creating, moving, or retiring a file, read
[Artifact Placement](ARTIFACT_PLACEMENT.md#置き場ルール). A document addition,
split, move, or deletion also follows its linked naming and reference owner.
An existing in-scope path does not require a repository placement survey.

Use run-local artifacts only for selected coordination or resumption. Durable
canonical documents stay with their responsibility owner; reusable findings
stay in the topic notes or authorized private log. When the selected handoff
uses document packets, preserve its cross-cutting, design, implementation, and
workflow/subagent packet order.

## Codex-Specific Rules

[AGENTS.md](../../AGENTS.md) remains the source entrypoint; canonical Skills and
generated/discovered adapters retain the [Skill Paths](skills.md#skill-paths)
ownership split. Role, model, write-scope, and lifecycle details are read from
[Codex Subagents](CODEX_SUBAGENTS.md) when delegation is selected. Reviewer
candidates require a distinct unresolved claim/risk; reuse an active reviewer
that owns the same claim and context. Multiple writers need dependency-expanded
disjoint scope, integration order, and collision-safe checkout ownership.

Before implementation, settle the owner/design decision using
[Design Integrity Gate](CODEX_IMPLEMENTATION.md#design-integrity-gate). Read
coordination-specific design and review artifacts only when selected. Carry
reusable rules into the existing canon rather than runtime-only duplicates.

At delivery, use [Completion Readiness](CODEX_COMPLETION.md#completion-readiness)
for the already selected route. Decide commit and push separately under
[delivery ownership](ROOT_DELIVERY.md#commit-and-push-decisions). A sharing,
handoff, remote-backup, or PR purpose with existing authority permits the chosen
push without another permission round trip. Record explicit no-push instructions
or actual blockers. A standalone branch transport retains its exact remote,
branch, commit/tree, SHA ref push, remote readback, and unchanged local identity
evidence; it does not claim PR lifecycle or merge readiness. PR mutation uses
[pr-processing](../skills/pr-processing.md).

Only coordination materializes its declared `verification.txt`,
`closeout_gate.md`, and `user_request_contract.md`. Bounded delivery records the
same required outcomes and actual selected results in the existing task/Issue;
file-backed coordination artifacts are not its completion prerequisites.
