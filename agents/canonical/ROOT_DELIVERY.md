# Evidence and delivery

<!--
@dependency-start
contract agent-runtime
responsibility Owns detailed source-side Issue evidence, task continuation, reporting, and publication guidance.
upstream design ../../AGENTS.md conditional source reader map
upstream design ../../ROOT_AGENTS.md portable common boundaries
upstream design ../../documents/design/entrypoint-owner-map.md source and consumer split contract
upstream design ../internal-routines/verification-result-structuring.md mandatory pre-write result structuring
@dependency-end
-->

Read the section selected by the source [AGENTS.md](../../AGENTS.md) Reader Map
when its responsibility is active. This is source-side detail, not an
additional startup packet or a dependency of generated consumer instructions.

## Observed runtime failures

An observed runtime failure of an AgentCanon-owned invariant is reportable in
the same task as the observation. The first record does not wait for a repeated
occurrence, dashboard evidence, repair completion, or confirmed cause; preserve
the error, command or action, snapshot, expected behavior, actual behavior, and
any unresolved hypotheses through the applicable Issue owner. Generic host,
dotfile, credential, consumer, or ownership-unknown failures stay with their
applicable owner or qualified handoff and are not attributed to AgentCanon by
proximity. This common base exposes that reporting scope without selecting an
external checkout, credential, or publication implementation.

## Feasible Issue evidence

When authoring, revising, or reviewing Issues, do not make completion depend on
empirical measurements that cannot be obtained within the authorized scope.
Require a measurement only when it is decision-relevant and its data, method,
and authorized execution route are identifiable from available facts; do not
add environment discovery or a new preflight gate to establish this. Do not
demand unrecorded historical baselines, unavailable internal telemetry,
uncontrollable comparisons, or finite observations as proof of permanent
non-recurrence. Use evidence appropriate to the claim, such as specifications,
mathematical or engineering analysis, source review, or reproducible tests,
and state what it establishes and its limits. Correct unnecessary or infeasible
measurement clauses with reasons in the existing Issue, preserving unmeasured
outcomes as limitations rather than automatic completion blockers or mandatory
follow-up Issues. Do not merely relabel such clauses as pending or needing
verification. A measurement required by the explicit request or governing
contract cannot be silently waived: keep the affected claim unverified, record
the concrete constraint and any feasible next step, and continue independent
work without claiming full completion. An unrun measurement in this session
alone does not establish infeasibility. Never present estimates, proxies, or
static checks as empirical results, or claim unmeasured improvement. Keep this
judgment with the applicable Issue and validation owners; do not add unrelated
instrumentation, environment setup, or reporting machinery to satisfy it.

## Continuation and blockers

A progress update is not a final report. Keep the request active while required
implementation, validation, integration, publication, cleanup, or its result
remains unresolved. An acknowledgement, apology, promise, child claim/handoff,
post-hoc healthy status, or incomplete result is not the requested operation or
its success. Preserve the request-to-actual-operation-to-result chain; after a
failure or incomplete result, the responsible owner continues with the next
safe authorized recovery or readback operation, without repeating an already
sufficient operation. Continue investigation only for an unresolved fact that
could change the requested implementation, required validation, or conclusion.
Reuse still-applicable evidence instead of repeating classifications or adding
unrelated prerequisites; once the fact is resolved, proceed with the work.
New relevant evidence can reopen a question. Required authorization, safety
checks, and selected validation remain in force.
If no such operation is authorized or possible, keep the task non-terminal and
report the concrete authority or external blocker with
its evidence and next owner/action. This does not require infinite retries or a
second completion state machine.

## Result reporting

Before any verification-result output, including chat progress and interrupted
handoffs, invoke [verification result structuring](../internal-routines/verification-result-structuring.md).
Use its retained findings and coverage check for the following report.

A result report leads with the answer to the user's request, not an inventory
of work. Explain whether the goal was met or what the investigation establishes,
what changed relative to the relevant baseline, and why that matters for the
user's use or decision. Connect decisive evidence to the conclusion and explain
what it proves and does not prove; file lists, command success, test counts,
status labels, and PR links are supporting details, not the answer.
Scale detail to useful findings and decision complexity, not elapsed time or
tool counts; preserve the internal routine's finding coverage and scope boundary.
Distinguish observations from inference and implemented, verified, published,
and applied states. State material uncertainty or remaining work and how it limits the
conclusion or safe use; do not claim unmeasured benefits. When a user decision is
needed, give the concrete choice, recommended option, rationale, and material
tradeoffs. When none is needed, say so rather than inventing a follow-up or
returning unfinished in-scope work to the user. For Issue-backed work, preserve
comparable rationale, evidence, limitations, and any next owner/action in the
existing Issue comment; links support rather than replace the chat conclusion.
Keep pre-write structuring mandatory without adding fixed headings, minimum
length, empty fields, or a separate approval gate.

## Commit and push decisions

At each coherent work boundary in a repository-changing task, decide whether
to commit and whether to push as separate operations. Commit a coherent,
reviewed unit after the selected validation when the request and ownership
support it; if the work is incomplete or mixes user-owned changes,
preserve it and state the concrete reason and next condition in the existing
work log or final status. Decide push independently from its sharing,
handoff, remote-backup, or PR purpose, the existing authority, and the
designated destination. Read-only, local-only, no-push, no-change, and genuine
external-failure cases remain valid. Do not force-push, mutate `main`, overwrite
unknown user files, create a new remote, or merge across scope. A committed but
unpushed child result is an intermediate handoff, not final publication; the
next authorized owner must launch the selected push operation when its purpose
and conditions are met. This is decision guidance, not an unconditional
commit/push gate or a new receipt requirement.

## Formatting and validation

Use the validation route owned by the changed repository-specific responsibility.
Formatting is part of completing edits, not an optional repair after lint fails.
Before final validation, staging, and commit or handoff, run the repository's
configured formatter on the task's edited files and review and include its diff.
Repeat after later edits, generation, fixers, or conflict resolution; an earlier
result does not cover changed content. A combined command that actually formats
the final files satisfies this step; tests or check-only lint do not. Preserve
unrelated or user-owned changes and the repository's existing formatting scope.
Do not add a formatter, configuration, hook, environment probe, or repository-wide
reformat to satisfy this rule. If no formatter is configured, do not invent one.
If the selected formatter fails or cannot run, record the command, affected files,
and reason in the existing Issue / PR or task result; hand off as unverified,
not as formatting-complete.

Validate the changed contract and its failure semantics, then use that owner's
closeout route when required. A generated consumer root file does not authorize
unrelated AgentCanon checks, product checks, or runtime changes.
