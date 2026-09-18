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

Run the configured formatter on final edits before validation or publication,
including after generation, fixes, or conflict resolution; review its diff.
Lint/tests are not formatting. Record unavailable commands and unverified
properties, never a false pass. Validate the changed contract through its owner;
other owners' examples are not a universal checklist. Do not add tools,
configuration, broad reformatting, or unrelated checks.
