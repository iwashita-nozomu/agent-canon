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
AgentCanon checkout or runtime is required. Source work uses its own owner map.

## Reader Map

Use the applicable repository's specific instructions and selected owner.
Read only details needed for the current action; indexes, links, and dependency
metadata are not full-reading obligations. Reuse unchanged context. Keep all
auto-loaded instructions short; place procedures in conditionally read files.

## Always-On Boundary

Stay within the authorized task and preserve unknown user/Git state. Preserve the
required problem class, valid inputs, guarantees, and failure semantics; neither
small diffs nor completeness justify shortcuts or unrelated work.

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
require error analysis rather than arbitrary offsets or tolerances. Retain outputs,
diagnostics, and actual status, including NaN/Inf or nonconvergence; stopping or
failed validation does not authorize hiding/discarding results or claiming success.

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

A leading `@ROOT_AGENTS.md` explicitly requests this base once; it is not a native
include. Continue through the specific owner map without restarting intake.
AgentCanon maintenance does not authorize changes to a consumer's generated files.

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
do not add tools, configuration, broad reformatting, or unrelated checks.
