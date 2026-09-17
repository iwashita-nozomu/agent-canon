# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the common, source-free base for consumer and source-specific repository root AGENTS.md files.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and common/source composition boundary
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
downstream implementation tools/agent/templates/entrypoint_composer.py composes the regular consumer root file
downstream implementation tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates the base grammar
@dependency-end
-->

This common base supplies shared entry behavior for consumer and source-specific
repository roots. It does not own task procedures, command recipes, role
lifecycles, implementation policy, validation schemas, or source-editing policy.

## Repository Role

A consumer owns its product source, build environment, tests, documentation,
CI, credentials, runtime semantics, and instruction extension. Its root
[AGENTS.md](AGENTS.md) is a regular tracked file composed from this base and its own
specific instructions, usable without an AgentCanon checkout or runtime.
Composition is not a live projection, runtime import, updater, vendor checkout,
submodule, or symlink.

The AgentCanon source checkout owns its source and canonical owner map. Its
source-specific [AGENTS.md](AGENTS.md) takes precedence for those responsibilities;
this base's consumer maps and routes do not redirect source work. Details stay
with the applicable repository's specific instructions and canonical owners.

## Reader Map

For a consumer root, use the [Runtime Owner Map](#runtime-owner-map) below and
the appended consumer-specific instructions. For a source-specific root, use
that checkout's [AGENTS.md](AGENTS.md) Reader Map and canonical owners.

## Always-On Boundary

The explicit user request and repository-specific canonical owner govern the task.
Preserve unknown dirty, staged, untracked, branch, and worktree state; do not
mutate it without the applicable Git owner's authorization. Keep work within the
authorized scope; unrelated findings may be reported, not silently added to it.

Preserve the required problem class, valid input domain, output guarantees, and
failure semantics. A bounded change does not authorize fixed dimensions,
restricted distributions, skipped valid cases, truncation, or projection chosen
for implementation convenience. Method limitations remain implementation gaps;
only explicit user direction may narrow the contract. Validate cases beyond the
motivating example, including those a shortcut would exclude.

Prefer the simplest complete implementation through direct use or composition
of existing APIs. Add concepts, state, branches, abstractions, configuration, or
dependencies only for an evidenced current gap, with mathematical or engineering
grounds; hypothetical reuse, uniformity, or test doubles do not justify them.
Neither smaller diffs nor completeness authorize omitted behavior, speculative
generalization, or unrelated changes. Before code/API changes, record necessity
in the owning durable design: requirement and caller, the unmet need without the
change, assumptions and grounds, existing APIs and simpler alternatives. Explain
removals too; reuse current design by reference and connect it to implementation
units in the same PR. Chat, Issue/PR text, signatures, or generic safety claims
do not replace this rationale. Reconsider unjustified code instead of inventing
reasons or adding documentation, checker, schema, or approval machinery.

Inspect the actual owner, caller, public API, nested configuration, and extension
points before library edits. Keep use-case orchestration, environment setup, and
presentation with callers. Change a reusable library only for an in-scope defect
or missing capability in its own contract; one caller can establish a defect.
Do not hide such defects in caller workarounds or add wrappers for convenience.
Record the owner choice and rejected alternative in the existing Issue/PR.

Use native dependency resolution. Do not add precautionary version pins,
hard-coded SHAs, or equality guards. New exact constraints require an explicit
requirement or demonstrated compatibility, integrity, or reproducibility need
at the dependency owner. Preserve required locks, gitlinks, and integrity checks;
recorded resolved versions/SHAs are evidence, not new execution constraints.

Before guards, retries, or fallbacks, establish the triggering input/state and
reachability under the contract from observation, specification, code, or analysis.
Separate possible, invariant-excluded, and unknown conditions: no incident does
not prove impossibility, and speculation does not prove possibility. Investigate
unknown premises; do not implement handling for excluded conditions or require
an incident/unsafe reproduction when analysis suffices. Close only an evidenced
gap with the smallest remedy and targeted validation. Avoid redundant checks or
stricter environment/layout/version restrictions where capability suffices;
optional diagnostics must not block supported work. Preserve authorization,
safety, and external-boundary validation and record grounds with existing owners.

Use the owning repository's configured entrypoint and standard defaults. Do not
manually select host/container, OS, CPU/GPU, runtime, or profile for ordinary work,
solicit optional settings, rediscover environments/tools at startup, or replace
this with new detection, flags, wrappers, fallback paths, or cached state. Reuse
applicable context. Diagnose only an explicit request, actual relevant failure,
changed required premise, or evidenced risk, and stop when the decision-relevant
fact is resolved. Diagnosis does not authorize setup/repair. Environment changes
and rebuild acceptance must belong to the requested scope. Preserve permissions,
safety checks, resource limits, and rerun prohibitions; contrary current evidence
overrides prior success. Record concrete blockers, stop only affected commands,
and continue independent work without switching required backends or weakening
validation. Never report an unrun command as passed.

For numerical discrepancies, check the algorithm and implementation against the
equations/specification, assumptions, units, indexing, update order, and boundaries
before numerical adjustment. Do not mask unexplained errors with offsets, clipping,
arbitrary epsilons, or relaxed tolerances. Rounding/conditioning/approximation
remedies need error analysis after algorithmic correctness checks, validated by
an independent reference or invariant. Never discard, overwrite, hide, or withhold
produced results merely for NaN/Inf, nonconvergence, or tolerance failures: retain
original outputs, diagnostics, and actual status with interpretation limits.
Retention does not declare correctness or override required stopping, safety, and
test-failure semantics; stopping does not authorize loss of prior results.

Establish cwd, Git root, branch, HEAD, and the selected owner's dependency/consumer
edges, including actual task workspace clones, not just declared pins. For each
in-scope edge, read resolved path, repository, branch/detached state, HEAD, dirty
state, and any required pin against the source used by execution. Do not infer
no dependency from no inspection or equate development and pinned checkouts.
Re-read affected identity after directory/branch/dependency/PR revision/pin/source
changes, not unchanged commands. When an existing consumer contract requires a
pin, use the published dependency PR commit through that pin before consumer
execution; otherwise preserve native resolution. Distinguish dependency-local
and consumer validation; unknown/mismatched inputs are not pinned verification.
This introduces no AgentCanon dependency into a source-free consumer.

Remove an unneeded task-owned temporary checkout through its cleanup owner once
no active work or unpreserved local state depends on it. Preserve unknown/user
clones; record removal or a concrete retention reason. This does not authorize
remote-branch or shared-workspace deletion. Before branch/annex work, read the
applicable branch/storage owners and separate Git metadata from annex payload.
Before team formation/change/delegation, read the team owner and orchestration
skill for logical role, model/profile, skills, authority, and handoff. Candidates
are not activations, and logical coverage is not an instance count. Consumer
owners remain self-contained, without source-path imports.

Record an observed AgentCanon-owned invariant failure in the same task without
waiting for repetition, confirmed cause, dashboard evidence, or repair. Preserve
error/action, snapshot, expected/actual behavior, and hypotheses through the Issue
owner. Host, credential, consumer, or unknown-owner failures require qualified
handoff, not attribution by proximity. Require Issue measurements only when
relevant and obtainable by an identifiable authorized route; do not demand missing
historical baselines, unavailable telemetry, uncontrolled comparisons, or proof of
permanent non-recurrence. Use claim-appropriate evidence and its limits; correct
unnecessary/infeasible criteria with reasons instead of merely marking them pending.
Explicitly required measurements cannot be waived: keep the claim unverified,
record constraints/feasible next action, and continue independent work. Unrun does
not mean infeasible; estimates/static checks are not empirical results. Do not
add instrumentation, environment setup, or gates solely to satisfy such criteria.

## Runtime Owner Map

For a consumer root, use only the following consumer-owned map:

| Responsibility | Consumer-root canonical owner | Validation / reader route |
| --- | --- | --- |
| product implementation and behavior | consumer source and design owners | consumer implementation route |
| build, tests, and runtime environment | consumer build and test owners | consumer execution route |
| repository structure and file placement | consumer structure owner | consumer structure route |
| root instruction extension | consumer-specific section in this file | consumer instruction route |
| AgentCanon source maintenance (consumer roots) | selected AgentCanon development checkout | AgentCanon maintenance route |
| observed AgentCanon runtime defect | applicable repository-specific Issue owner | immediate Issue record or qualified no-mutation handoff |

## Task Entry

Resolve the task owner and validation oracle through the applicable Reader Map.
For AgentCanon changes from a consumer root, select a separate qualified
AgentCanon development checkout. Keep consumer trees unchanged unless the
consumer task explicitly owns the resulting generated file.

When a root [AGENTS.md](AGENTS.md) begins with the literal `@ROOT_AGENTS.md`, read this
common base first and then continue into that file's source- or consumer-specific
Reader Map. The marker is a reference for the reader, not a claim of automatic
expansion or runtime import.

A progress update, child handoff, apology, or healthy later status is not task
completion. Continue required implementation, validation, integration, publication,
and cleanup through the next safe authorized operation, without repeating sufficient
evidence. Investigate only unresolved facts that can change implementation,
validation, or conclusions; reopen them only for new relevant evidence. When no
safe authorized step is possible, keep the task non-terminal and report the concrete
blocker, evidence, and next owner/action, without infinite retries or new gates.

Report the answer and user-relevant change first, with decisive evidence and what
it does and does not prove. Retain material findings, counterevidence, rejected
explanations, and unresolved points even without a code change; out-of-scope
findings do not authorize repair. Distinguish observation/inference and implemented,
verified, published, and applied states. Explain uncertainty and safe-use limits,
not unmeasured benefits. Give a justified recommendation only when a user decision
is needed; do not invent follow-up work. Preserve comparable reasoning, evidence,
limitations, and next actions in the Issue comment, not links alone. Scale detail
to useful findings, without fixed headings, length quotas, or a reporting gate.

Decide commit and push separately at coherent work boundaries under the existing
authority and selected validation. Preserve incomplete/mixed user-owned work and
record the reason and next condition. Push when its sharing/handoff/backup/PR
purpose, authority, and destination support it; a child's unpushed commit is not
publication. Read-only, local-only, no-push, no-change, and external-blocked cases
remain valid. Do not force-push, mutate main, overwrite unknown files, add a remote,
or merge across scope. These decisions are not unconditional commit/push gates.

## Validation Routing

Use the changed responsibility's existing validation and closeout owners. Run its
configured formatter on edited final files before final validation, staging,
commit, or handoff; review and include its diff. Repeat after edits, generation,
fixers, or conflict resolution. Tests/check-only lint are not formatting; a combined
command that actually formats final files suffices. Preserve unrelated/user changes;
do not add a formatter, configuration, hook, environment probe, or repository-wide
reformat, and do not invent a formatter where none is configured. A failed/unavailable
formatter requires the command, affected files, reason, and unverified status in
the existing Issue/PR/result, not a formatting-complete claim. Validate the changed
contract and failure semantics; generated consumer instructions do not authorize
unrelated AgentCanon/product checks or runtime changes.
