# Evidence and delivery

<!--
@dependency-start
contract agent-runtime
responsibility Owns detailed source-side Issue evidence, task continuation, reporting, and publication guidance.
upstream design ../../AGENTS.md conditional source reader map
upstream design ../../ROOT_AGENTS.md portable common boundaries
upstream design ../../documents/design/entrypoint-owner-map.md source and consumer split contract
upstream design ../internal-routines/verification-result-structuring.md verification findings and completion reporting
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
proximity. This common boundary exposes reporting scope without selecting an
external checkout, credential, or publication implementation.

Verification failures use actual outputs and the current conversation for diagnosis.
A separate failure topic, work log, or per-attempt record is not required.

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

Follow [Task Entry](../../ROOT_AGENTS.md#task-entry) when work remains. Use
[bounded diagnosis](ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis)
for a fact that could change the implementation, validation, or conclusion.
When authorization or external conditions block the next action, report the
concrete blocker, its evidence, and the owner who can resolve it.

## Reader-facing writing

State the established facts, their sources, and the resulting conclusion.
Explanatory documents link to the existing sources for procedures and execution
conditions. Use [terms and translation](../internal-routines/verification-result-structuring.md#terms-and-translation)
for terminology and [Japanese revision](../internal-routines/verification-result-structuring.md#japanese-revision)
for Japanese prose.

## Result reporting

[検証結果の記述](../internal-routines/verification-result-structuring.md#structure-before-writeout)
と [完了報告](../internal-routines/verification-result-structuring.md#completion-reports) に従います。
ユーザーの判断が必要な場合は、確認した事実、選択肢と結果、推奨案の理由を示します。

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

Apply the common root's [Validation Routing](../../ROOT_AGENTS.md#validation-routing)
at each editing-batch boundary and before final validation, staging, commit,
publication, or handoff. Source configuration and direct commands belong to
[Formatter settings](../../documents/design/formatting.md#ownership-and-purpose).
Record the actual command, target files, and result, including success, in the
existing task/Issue. Run the affected check on the final files after any later edits.

Select the current result's [validation and delivery route](CODEX_COMPLETION.md#reader-map).
The changed contract and its failure semantics determine the checks. A bounded route
uses its existing evidence; only selected coordination consumes run-bundle closeout.
A generated consumer root does not authorize unrelated AgentCanon or product checks,
runtime changes, or a different formatter.
