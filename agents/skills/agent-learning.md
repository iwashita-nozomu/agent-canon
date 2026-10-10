# agent-learning

<!--
@dependency-start
contract skill
responsibility Routes private knowledge and feedback to the external log owner and applies selected behavior-learning decisions.
upstream design ../../documents/runtime/private-feedback-knowledge.md private log command and storage contract
upstream design ../../documents/operations/notes-lifecycle.md public failed verification and topic reuse
upstream implementation ../../tools/runtime/archive/private_feedback.py metadata-only private log adapter
downstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py runtime feedback evidence
@dependency-end
-->

## Reader Map

Choose the record's owner before reading an operating procedure. The public
catalog's private-knowledge/feedback and behavior-learning description is the
activation boundary for this Skill.

| Current need | Read next |
| --- | --- |
| Record or reuse a public repository-specific verification failure | [Notes Lifecycle](../../documents/operations/notes-lifecycle.md#failed-verification-record), or [Retrieve Before Deciding](../../documents/operations/notes-lifecycle.md#retrieve-before-deciding); return to the current task |
| Search, record, read back, or synchronize private knowledge / feedback | [Operating Route](#operating-route) |
| Feedback requires a decision about agent behavior, active Skills, or recurrence | [Mandatory Behavior and Learning Contract](#mandatory-behavior-and-learning-contract), then the selected record operation |
| Finish the selected recording or learning operation | [Closeout Decision](#closeout-decision) |

Saving a public failure memo does not activate private capture, calibration, or
behavior evaluation. A private knowledge lookup does not require a behavior-eval
run. When one task genuinely needs both, preserve their distinct results and
reuse existing records rather than capturing the same observation twice.

## Purpose

Keep independent private problem-solving knowledge and feedback in authorized
`agent-canon-log` topics. Stable rules belong to their canonical owner; private
knowledge is neither a second public canon nor raw chat copied into the source tree.
Public failed verification remains with the existing topic-note owner above.

## Use When

Use when private knowledge/feedback curation, an explicit private recording request,
or evidence-backed agent behavior learning is active. Relevant causes include a
routing miss, weak Skill invocation, reviewer feedback, or a task retrospective
that changes a future execution decision. Public topic recording alone follows
Notes Lifecycle directly.

## Core References

- [Private log contract](../../documents/runtime/private-feedback-knowledge.md)
- [Notes Lifecycle](../../documents/operations/notes-lifecycle.md)
- `tools/runtime/archive/private_feedback.py`
- `tools/runtime/lifecycle/workflow_monitor.py`
- `eval/definitions/agent_behavior_eval.toml`

## Mandatory Behavior and Learning Contract

Read this section when behavior feedback requires calibration or evaluation.
Separate stable user preferences from observations; record source, evidence,
scope, confidence, and the decision rather than a raw transcript. Stable preferences
are explicit changes to the relevant AGENTS or canonical owner, not private canon.

Use `workflow_monitor.py` for its existing behavior-event and runtime-feedback
schemas. Skill invocation, subagent routing/lifecycle, tool gates, prompt evaluation,
review feedback, and diff-check decisions retain their event owner. Select the
affected Skill, prompt, workflow, evaluation, or knowledge owner from the evidence.
The active Skill set is the first calibration candidate for an observed Skill gap;
record the repair and its validation, or the evidence supporting unchanged behavior.
A single observation normally becomes scoped guidance or an example; a hard rule
requires a repeated observation or a checker-backed invariant.

Use the evaluation owner and `agent_behavior_eval.toml` only for a selected behavior
evaluation or a changed behavior contract that requires it. Preserve feedback action,
calibration decision, selected validation, and unresolved handoff in the existing
task record. Do not duplicate event fields, require a new decision token, or run
all behavior evaluations to save an ordinary knowledge topic.

## Operating Route

Use this section for authorized private knowledge/feedback operations. Commands are
logical commands carried through the current context's
[existing execution route](../canonical/CLI_ENTRYPOINTS.md#tool-commands).

1. Identify the purpose/candidate, source revision, relevant conditions, expected
   and observed result, reproducible command or inspection, evidence locator,
   verified conclusion, and reuse/recheck conditions. Keep established cause distinct
   from a failure observation. Resolve a cause needed for the current decision through
   the owning investigation and add the result to the same topic.
2. Before adopting or rejecting a candidate, use `agent-canon k search --query
   <relevant-evidence>` and `k read <topic>` for relevant existing private knowledge.
   Compare inputs, revisions, configuration, and guarantees. Reuse results under
   unchanged premises; verify changed decision-relevant premises. Search failure or
   an unperformed search is not evidence that no topic exists.
3. Choose one existing capture. Independent feedback uses `agent-canon f add <topic>
   --stdin`; reusable knowledge uses `agent-canon k add <topic> --stdin`. Use the
   behavior owner's runtime-feedback operation for its structured events, without
   duplicating the same observation into runtime-feedback, f, and k. Update an
   existing topic for the same problem and link later correction or counterevidence.
4. Read back this record and its operation receipt with `k/f status` and targeted
   `k read` or the owner-supported feedback readback. A spool write is not remote
   publication. When synchronization is needed, execute existing `k/f sync` and
   verify that operation's result; a healthy global status or another record's
   success does not prove this record arrived.
5. An authorized stable-rule promotion updates the existing canonical owner and
   reads back that change. It does not copy permanent policy into private knowledge
   or automatically publish private text.

Keep the original receipt/record identities and the owner's retention/retry rules.
Private content stays outside public Issues, PRs, dashboards, source files, and
handoffs; use an authorized locator and a publishable finding instead.

## Evidence Boundary

| Evidence | Owner |
| --- | --- |
| Raw runtime event, transcript, chronology | runtime archive / evidence owner |
| Actionable repository defect | repository-qualified GitHub Issue |
| Public failed verification and reproduction | `documents/notes/failures/` topic record |
| Reusable private knowledge or feedback | authorized private `agent-canon-log` topic |
| Permanent shared rule | owning canonical document / AGENTS |

## Closeout Decision

Read back the exact record saved or reused in this task. Preserve the operation,
result, evidence location, conclusion and reuse conditions, and distinguish saved,
synchronized, and verified remote states. `no_op` requires evidence such as an
already-saved identical observation; write failure is not a no-op.

For the selected behavior-learning branch, also resolve or explicitly hand off the
feedback action (`prompt_repair`, `eval_update`, `knowledge_record`, or `no_op`),
calibration decision, and any selected behavior-eval result. Other branches finish
with their record/search result and do not inherit this evaluation obligation.

An unavailable entrypoint or a failed search/write/sync/readback is recorded with the
actual attempted operation, observed result, unperformed scope, and next owner/action.
Keep saved spool with its owner. Do not claim unsaved content is saved or put private
text in public source as a fallback. Unrelated runtime repairs, a new conversation,
or a whole evaluation rerun are not prerequisites for independent recording work.

## Runtime Contract Clauses

Use the matching Reader Map branch in the task that activates it. Preserve topic
search before a private adoption/rejection decision and exact-record readback after
writing. Public failure recording retains the Notes Lifecycle contract. Behavior
calibration/evaluation applies only under its own condition, and each output reports
the actual result and limitations through the existing task/Issue owner.
