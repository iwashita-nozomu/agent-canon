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
AgentCanon checkout or runtime is required. Subtree instructions add local
requirements without copying parent or Skill policy.

## Reader Map

Read applicable repository instructions and the selected owner. Consult an index
only when the owner is unresolved; follow conditional references when needed.
Reuse unchanged context and evidence rather than restarting discovery.

## Always-On Boundary

The latest explicit user agreement defines the requested outcome, acceptance, and
authority. Confirm the checkout and relevant revision; preserve unknown Git state
and user data. Task authority does not authorize unrelated changes or publication.
Current explicit instructions in the conversation take precedence over repository
and Skill guidance or past procedures, subject to higher-priority system and
developer instructions. For code cleanup, reduce the relevant owning
implementation; do not add features, wrappers, or safety code. Deleting unrelated
documentation or artifacts does not offset source growth. Genuine functional
expansion requires separate agreement from the current user.

For a local repair, start from the target code, diff, and governing contract;
do not make use-site or out-of-scope investigation a prerequisite. If those facts
cannot resolve a concrete decision, state the missing fact and smallest reference
needed. For an explicitly cross-module change or API migration, use only its
declared dependency scope.

Carry authorized work through the requested outcome. Base implementation on
the current request and target's input/output contract while preserving external
boundaries. Earlier implementations and diffs can explain behavior, but do not
define correctness; restore prior behavior only when the current requirement
calls for it. For consequential behavior changes, briefly record at the existing
owner location why the change was needed, why the prior approach did not fit,
and what behavior is intentionally retained or retired; use that rationale when
reconsidering later changes or restoration. On failure, compare expected and
actual inputs/outputs and check what the target received or consumed. Use
history as cause evidence and inspect only the relevant target boundary. For an
authorized repair, fix the located cause and rerun the selected route. When
that diagnosis or repair interrupts other requested work, retain its target,
interrupted operation, and acceptance in the existing task or handoff, then
return to that target and continue the interrupted work. Cause-local success
does not establish the requested outcome. Do not add speculative guards,
fallback paths, retries, or gates without a concrete cause. Do not alter tests
or switch routes merely to obtain a pass.
When a separate responsibility fails, compare its actual and expected inputs
and outputs with relevant completed behavior and its recorded purpose. Preserve
shared purpose and invariants while distinguishing changed inputs; consider
whether required valid cases fit the existing contract, type, interface, or
abstraction, and extend it when needed. Change prior behavior when current
requirements and this comparison identify a concrete cause; do not add layers
for hypothetical inputs.
Keep observations, causes, and unverified results distinct.
Use configured Git/GitHub transports. Do not discover, create, copy, link, or
configure credentials or auth agents; return authentication failures to their
transport owner.

For experiment repositories, keep `main` to shared models/helpers, execution and
regression infrastructure, completed `summary.md` files, and archive references;
keep each experiment branch to that topic's code/config. This boundary does not
prohibit normal product code on `main`. Put active raw logs in ignored scratch,
preserve reproducibility inputs and the execution commit, then archive selected
evidence with a retrievable summary of its method, commit, results, and limits.
Retire topic or disposable diagnostic code only after retaining the summary.
Treat closed verification/diagnosis separately from active experiments.

## Runtime Owner Map

| Responsibility | Consumer owner |
| --- | --- |
| product implementation and behavior | consumer source and design owners |
| build, tests, and runtime environment | consumer build and test owners |
| repository structure and file placement | consumer structure owner |
| root instruction extension | consumer-specific section in this file |
| AgentCanon source maintenance | selected AgentCanon development checkout |

## Task Entry

The selected workflow owns execution, delegation, and validation. Activate design,
research, or specialist routes only when their conditions apply. AgentCanon source
maintenance does not authorize editing a consumer's generated instructions.

For authorized implementation or repair, complete the requested in-scope outcome,
including existing failures; diagnosis, checkpoints, and no-op checks alone do
not complete it. Honor explicit stop boundaries. Keep independent problems in
separate repair units: each owner carries its active unit through the requested
result and required check before taking another; independent units may proceed in
parallel. If blocked, report the failed operation, unverified property, and next
owner/action, and finish independent work.

Report commit and push separately, and distinguish implemented, verified,
published, and applied states. Ground claims in source, a checked derivation, or
the owner's operation; state material uncertainty and limits without exposing
secrets.

## Validation Routing

Select validation from changed guarantees. Include consumer checks when the
request explicitly migrates those consumers. Reuse unchanged results; run broader
suites only when those guarantees require them. Format the final edited files
with the configured formatter before delivery, including its diff; unavailable
formatting remains unverified. Tests, observations, and proofs establish
different properties: report what was actually established.
