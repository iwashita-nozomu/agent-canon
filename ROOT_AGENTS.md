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
metadata are not full-reading obligations. Reuse unchanged context. Keep all
auto-loaded instructions short; place procedures in conditionally read files.

## Always-On Boundary

Stay within the authorized task and preserve unknown user/Git state. Preserve the
required problem class, valid inputs, guarantees, and failure semantics; neither
small diffs nor completeness justify shortcuts or unrelated work. Follow the
selected owner rather than inventing a fallback, wrapper, or policy copy.

Public API additions/extensions (exports, types/methods, endpoints, parameters,
CLI commands/options) require explicit user authorization for that public change;
a general feature/fix/cleanup request is insufficient. First investigate existing
APIs, configuration, extensions, standard facilities, and adopted dependencies on
the premise they suffice. Use them when they do; otherwise record candidates,
source evidence, the unmet contract, and why composition fails in the owning
design. Necessity is not authorization, and missing evidence is not a gap.
Without both evidence and authority, keep the addition a proposal and continue
independent authorized work. Reuse prior explicit approval; internal fixes and
existing-API use require no new approval system or check.

Prefer the simplest complete use of existing APIs. Put necessity, mathematical
or engineering grounds, and rejected simpler alternatives in the owning design
before code/API changes. Inspect real callers, APIs, configuration, and extension
points; keep caller orchestration separate from reusable-library responsibility.
Add mechanisms, dependencies, exact pins, or guards only for an evidenced current
need, not speculation. Preserve native resolution and required integrity checks.
Establish reachability and existing guarantees before extra error handling;
unknown is neither impossible nor a defect. Keep authorization and boundary safety.

Use configured execution and defaults. Do not rediscover or manually switch
environments, add probes/fallbacks, or rebuild for ordinary work. Diagnose only
requested or evidenced relevant problems; stop when the decision is resolved.
Repair requires scope and authority. Block only affected actions, preserve resource
and rerun limits, and never replace a required backend to claim validation.

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

Continue safe, authorized implementation through delivery; report concrete blockers
and the next owner when stopped. Separate commit/push authority and preserve mixed
work; never force-push, mutate main, or publish outside scope. Report the result,
material findings, evidence, and limits; distinguish implemented, verified,
published, and applied. Keep comparable reasoning and results on the Issue.

## Validation Routing

Use the validation route owned by the changed repository-specific responsibility.
Examples or commands in another owner are not a universal checklist.
Run the repository's configured formatter every time an editing batch ends,
before final validation, staging, commit, PR publication, or handoff. Formatting
is part of the edit, not optional repair after lint fails. Small changes,
documentation-only changes, and already tidy-looking files are not exemptions.
Run it on the task's edited files, review the resulting diff, and include it in
the submitted change. Repeat after any later edit, generation, fixer, or conflict
resolution; a previous run does not cover new content. A combined command that
actually formats those final files satisfies this step. Tests, check-only lint,
and an editor's format-on-save setting alone do not demonstrate that it ran.
Read-only work does not need a formatter run. Preserve unrelated or user-owned
changes and the repository's existing formatting scope; do not reformat the
whole repository for a bounded task.

Use tracked, tool-native settings selected by the repository owner rather than
personal defaults or ad-hoc command overrides. Do not introduce a formatter,
configuration, or hook during unrelated work; an explicit formatting-configuration
request may establish or change them at their owner. If no formatter is
configured, record that fact rather than silently choosing one. Do not add an
environment probe, wrapper, or new validation gate merely to enforce this rule.
Record the actual formatting command, target files, and result in the existing
Issue / PR validation record or task result, including successful runs. If the
selected formatter fails or cannot run, record the failure and affected scope;
hand off as unverified, not as formatting-complete.
Do not silently skip it or report static inspection as formatter execution.

Validate the changed contract and its failure semantics, then use that owner's
closeout route when required. A generated consumer root file does not authorize
unrelated AgentCanon checks, product checks, or runtime changes.
