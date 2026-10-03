# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the portable minimum shared by source and consumer roots.
upstream design documents/design/entrypoint-owner-map.md reading and composition boundary
downstream implementation tools/agent/templates/entrypoint_composer.py consumer composition
@dependency-end
-->

## Repository Role

Consumers own their product, environment, tests, credentials, and specific
instructions. Their generated [AGENTS.md](AGENTS.md) is self-contained; no
AgentCanon checkout or runtime is required. Specific owner maps take precedence
for their responsibilities, not over shared constraints. Local AGENTS add only
subtree-owned instructions, never copies of parent, workflow, or Skill policy.

## Reader Map

Use the applicable repository's specific instructions and selected owner.
Read only details needed for the current action; indexes, links, and dependency
metadata are not full-reading obligations. Reuse unchanged context. Keep each
file focused on a responsibility and its activation condition; route independently
needed details to their owner at the point of use, not a startup reading list.
Keep auto-loaded instructions short and shared constraints self-contained.

Order actions by the inputs they actually require, not by link direction or
document order. Never require an observation, generated result, or later approval
before the authorized action that produces it. Bounded observation may obtain
new evidence without a revised task; this does not authorize repeating a failed
mutation without changed premises. Preserve safety checks and stop only actions
whose actual prerequisites are unresolved.

## Always-On Boundary

Stay within the authorized task and preserve unknown user/Git state. Preservation
is not abandonment: inspect Git inconsistencies, repair within task authority,
or hand off preserved state with a concrete owner/action. Unfamiliar diffs or
absent separate instructions do not waive this duty; dirty is not itself
inconsistent. Preserve the required problem class, valid inputs, guarantees, and
failure semantics; neither small diffs nor completeness justify shortcuts or
unrelated work. Follow the selected owner rather than inventing a fallback,
wrapper, or policy copy.

A requested root fix includes necessary public API replacement, removal, or
unavoidable addition and affected consumers, tests, and documentation. Fix the
root, then trace and repair affected uses; bound work by changed contracts, not
the initially named files. API preservation or active use is not a veto or a
separate-approval requirement. Respect explicit compatibility constraints and
actual authority/access limits; report concrete conflicts and unfinished migration
while continuing independent authorized work. Unrelated or speculative API
additions still require explicit authorization.

Start from the latest explicit user agreement, including the preceding chat;
update the owning design to that target, not the target to existing code.
Existing code, tests, or older design are evidence of meaning and migration impact,
not a veto or a requirement to keep their shape. Separate required outcomes from
changeable API, representation, state, and responsibility contracts; compare
contract-and-implementation alternatives for mathematical simplicity before fixing
the design. Necessary contract changes include affected consumer migration, not a
separate approval merely for changing a contract. Preserve explicit guarantees,
compatibility, and authority; expose concrete conflicts rather than silently
weakening requirements or inventing compatibility.

Before implementation, including private helpers and in-file additions, inspect
relevant abstractions, callers, APIs, configuration, extension points, standard
facilities, and adopted dependencies against that target. For new functionality,
start with their direct use, configuration, and composition; implement only an
evidenced gap. For fixes, changes, or cleanup of existing functionality, reconsider
whether the affected structure should remain: consider removing or replacing
unnecessary or defective mechanisms before adding layers to preserve them.
Reuse sound parts; a fix does not require deletion or wholesale rewriting.
Apply these choices per responsibility in mixed tasks, not by file age or a
single label for the whole task. Keep necessity, source evidence, engineering
grounds, and rejected simpler alternatives in the owning design.
A failed name search is not absence; unknown defers only the affected decision.

Actively shrink maintained code space within the affected responsibility, not just
limit additions or minimize the diff. With the task-specific starting point above,
seek and apply evidenced deletion, consolidation, and simplification opportunities
in the same change; do not wait for a separate cleanup request. Prefer fewer
independent states, special cases, coupled invariants, and proof obligations,
including required caller conversions and support. Justify the governing laws
and representation correspondence; do not merely compress or relocate code,
force deletion quotas, or weaken required behavior, safety, or performance.
Establish semantics and migration before deleting; replacement removes obsolete code
and support while migrating necessary consumers in the same change.
Retain wrappers or dual paths only for a required compatibility contract. Keep
caller orchestration separate from reusable-library responsibility. Add mechanisms,
dependencies, exact pins, or guards only for an evidenced current need; preserve
native resolution and required integrity checks.
When an existing dependency contract requires an exact pin, only execution that
needs a dependency change uses a published PR commit through that consumer-owned
pin; otherwise use the consumer's declared resolution.
Establish reachability and existing guarantees before extra error handling;
unknown is neither impossible nor a defect. Keep authorization and boundary safety.

Run the repository owner's fixed execution route with configured defaults first;
success needs no route probes. After an actual failure, inspect only facts that
can change the next authorized action. Stop incidental environment diagnosis when
that decision is settled, scope/access prevents a remedy, or further inspection
offers no actionable evidence. Reuse unchanged failure evidence; a retry needs a
concrete changed premise and existing rerun allowance. Environment repair and
exhaustive cause proof are not prerequisites for independent authorized work.
Record blocked required verification and continue that work; warnings, optional
settings, and unavailable diagnostics do not create new gates.

Keep the fixed route through retries, validation, and handoff. Do not preflight,
manually switch environments, bypass the entrypoint, or invent scripts, workflows,
wrappers, or fallbacks. Fixed means the owned procedure, not hard-coded paths,
versions, or SHAs. Preserve the entrypoint's safety checks, permissions, resource
and rerun limits, and failure semantics. Route changes and repair require scope
and authority at that owner. Stop only affected actions; do not rebuild for
ordinary work or replace a required backend to claim validation. Explicit
diagnosis/setup requests retain their own scope.

Bound audits, reviews, and validation by the requested task; audit another backend
only when explicitly named or required by a cross-backend guarantee. Leave its
implementation, configuration, runtime, and logs untouched; do not run or repair
it for parity or completeness. Backend differences alone are not defects. For
shared changes, validate the changed shared contract without auditing unrelated
backend internals. Briefly record exclusions in the existing Issue/PR when
relevant; do not make them failures, verification debt, required follow-ups, or
completion conditions. Do not add probes, adapters, settings, or measurements
solely to audit an excluded backend. If a required in-scope backend is unavailable,
report it as unverified; do not substitute another backend.

Environment rebuilds include deleting the superseded environment and its exclusive
resources in the same task. Stopping, renaming, relocating, or keeping it for
backup/rollback is not completion. Migrate needed data through the existing
environment/storage owners, verify absence, and report failed cleanup as incomplete;
preserve current shared resources, user data, and unrelated state.

Check algorithms against equations and assumptions before numerical adjustments;
require error analysis rather than arbitrary offsets or tolerances. Report actual
status and limits; numerical symptoms alone do not establish research failure or
authorize discarding non-experiment results or unconfirmed experiment observations.
For protocol-confirmed failed experiments, immediately delete experiment-only
code, configuration, and artifacts unless evidence establishes a physical cause.
Unknown cause, debugging value, numerical trouble, or future reuse do not justify
retention or waiting for closeout. Use existing experiment/storage owners with
safe stopping and scoped authority; keep only a concise Issue/task disposition,
not a relocated bundle. Preserve successful/shared/other-owned data and Git
history. Do not add discard classifiers, archives, or reruns as cleanup gates.

Establish the actual in-scope checkout and dependency identities; recheck only
changed premises. Keep required pin evidence distinct from execution inputs.
Read Git/storage/team owners before those operations. Clean only unneeded,
task-owned temporary checkouts; preserve unknown state and shared resources.

Record observed AgentCanon-owned failures promptly through the Issue owner;
qualify uncertain attribution. Demand measurements only when relevant and
obtainable by an authorized route. Explicit but unavailable requirements remain
unverified; do not add setup, gates, or unrelated completion criteria.

## Runtime Owner Map

| Responsibility | Consumer owner |
| --- | --- |
| product implementation and behavior | consumer source and design owners |
| build, tests, and runtime environment | consumer build and test owners |
| repository structure and file placement | consumer structure owner |
| root instruction extension | consumer-specific section in this file |
| AgentCanon source maintenance | selected AgentCanon development checkout |

## Task Entry

Resolve the task owner and validation route. Keep bounded work bounded; broader
design, orchestration, research, or delegation activates only under its owner's
conditions. AgentCanon maintenance does not authorize consumer generated-file edits.

User-guided debugging is parent-executed: keep investigation, edits, and any
user-requested validation in the same parent session, without subagents.
This boundary overrides orchestrator-only and mandatory child-handoff rules
while that cadence is active; do not delegate through existing children or
parallel read-only work. Only an explicit user change of cadence returns to
autonomous routing.

All reader-facing writing, not only Issues or verification results, must let the
intended reader reproduce the relevant actions or reconstruct the stated reasoning
from the output and identified, accessible references, without private chat history
or the author's environment. Before writeout, walk through the reader's task:
provide applicable scope, prerequisites, exact inputs and ordered steps, expected
outcomes or decision method, and precise evidence locations. For designs and
explanations, expose definitions, premises, and the link from evidence to conclusion.
Resolve placeholders and necessary context; brevity or links alone do not excuse
missing information. Distinguish proposed, observed, unrun, and unknown conditions.
State unavailable or withheld evidence and its limits without inventing facts or
exposing secrets. Reuse existing owners and records; this writing obligation adds
no fixed template, environment discovery, rerun, or publication gate.

Continue safe, authorized implementation through delivery; report concrete blockers
and the next owner when stopped. Separate commit/push authority and preserve mixed
work; never force-push, mutate main, or publish outside scope. Report the result,
material findings, evidence, and limits; distinguish implemented, verified,
published, and applied. Before writing any verification result, including progress
or interrupted work, structure established facts, evidence, scope, and limits;
preserve distinct findings and counterevidence. Use that same result across chat,
Issue/PR comments, and reports through the applicable reporting owner. Keep
comparable reasoning and results on the Issue.

## Validation Routing

Use the validation route owned by the changed repository-specific responsibility.
Examples or commands in another owner are not a universal checklist.
Run the repository's configured formatter on edited files whenever an editing
batch ends, before final validation, staging, commit, PR publication, or handoff;
review and include its diff. Repeat after edits, generation, fixers, or conflict
resolution. Small, documentation-only, and tidy-looking changes are not exemptions;
read-only work needs no run. A combined operation that formats the final files
satisfies this rule; tests, check-only lint, static inspection, or format-on-save
settings alone do not. Preserve unrelated/user-owned changes and the owner's
formatting scope; do not reformat the whole repository for a bounded task.

Use tracked, tool-native owner settings, not personal defaults or ad-hoc overrides.
Do not introduce a formatter, configuration, or hook during unrelated work;
explicit formatting-configuration requests may establish or change them. Add no
probe, wrapper, or validation gate to enforce this rule. Record the actual
command, target files, and result, including success, in the existing Issue/PR
or task record. If no formatter is configured,
record that fact without choosing one. If it fails or cannot run, record the
failure and affected scope and hand off as unverified, not formatting-complete.

Base verification on deduction: derive obligations from requirements and explicit
assumptions before implementation; show invariant establishment and preservation,
composition, required termination, and outcomes against the actual code. Check
assumptions and model-to-runtime gaps; never assume the conclusion or narrow valid
inputs to make a proof pass. Tests target derived properties, counterexamples,
and integration gaps, not proof by examples. Retain required execution checks;
distinguish reasoned arguments, machine-checked proofs, observations, and unresolved
claims. Use existing validation and closeout owners without new universal gates.
A generated consumer root does not authorize unrelated checks or runtime changes.
