# Verification result structuring

<!--
@dependency-start
contract agent-runtime
responsibility Structures established verification results before reader-facing output without losing findings or re-owning publication.
upstream design ../../ROOT_AGENTS.md portable evidence and delivery boundary
upstream design ../skills/README.md internal skill visibility boundary
downstream design ../canonical/ROOT_DELIVERY.md chat and handoff output caller
downstream design ../skills/report-writing.md report drafting caller
downstream design ../skills/pr-processing.md Issue and PR publication caller
downstream design github-connected-work.md connected publication caller
downstream design README.md internal routine index
@dependency-end
-->

## Invocation and boundary

This internal skill must run before drafting, updating, posting, or saving any
reader-facing verification result: chat progress or final replies, Issue and PR
bodies or comments, reports, and handoffs, including interrupted or failed work.
Do not wait for all verification to finish. An acknowledgement or plan containing
no verification results does not activate it.

Callers use the same structured result from the existing task/Issue record,
not separate copies of this procedure. Reuse still-valid structure and evidence;
incorporate new facts and corrections before the next output. This is a
mandatory writing step, not a new approval, checker, ledger, or fixed template.
Optional document topology planning does not make this step optional.

| Caller | Output boundary |
| --- | --- |
| [Evidence and delivery](../canonical/ROOT_DELIVERY.md#result-reporting) | Chat progress, final result, and handoff |
| [Report writing](../skills/report-writing.md#source-packet) | Report draft or revision |
| [PR processing](../skills/pr-processing.md#publication-boundary) | Issue/PR body or comment |
| [Connected work](github-connected-work.md#use-and-boundary) | The same outputs through authorized GitHub tools |

## Structure before writeout

1. At normal work boundaries, retain established findings and evidence in the
   existing task/Issue record, rather than reconstructing them from memory at
   closeout. Before each output, reconcile that record with the results obtained
   so far. Organize each distinct finding using the relationships below. These
   are semantic relationships, not prescribed output columns or headings;
   no empty fields or serialization are required.

   | Relationship | Content |
   | --- | --- |
   | Established fact | What was observed or demonstrated; distinguish inference and hypothesis |
   | Evidence and conditions | Actual command/action and result, source/snapshot, input conditions, and existing evidence reference |
   | Meaning and scope | What decision the finding supports and what it does not establish |
   | Limits and contrary evidence | Failed or unrun checks, blockers, counterevidence, rejected hypotheses and reasons |
   | Disposition | Action taken, reason for no change or deferral, and next owner/action when needed |

2. Merge repeated observations, not distinct findings. Preserve each established
   in-scope result and material counterevidence even when no code change follows,
   it does not support the final conclusion, later verification fails, or the
   overall task is unfinished. Preserve unresolved hypotheses as hypotheses.
   When new evidence corrects a result, retain the correction and its reason;
   do not keep presenting the superseded claim as current.
3. Check both directions before writeout: each output claim has evidence or is
   labelled as inference, and each established finding has a place in the output
   or an explicitly identified retained record. Do not silently omit facts to
   shorten the response. Unrun is not passed, partial validation is not complete
   validation, and a document edit is not evidence of runtime behavior.
   For parent/worker execution failures, preserve process-local scope and
   counterevidence through the existing [execution diagnosis owner](../canonical/ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis);
   do not generalize a child's access failure into a host/environment defect.
4. Before drafting, [choose the presentation](#choose-the-presentation) from this
   structure. Write to the applicable, authorized destinations in the current task.
   Adapt presentation, not facts or their limits. For Issue-backed work, leave
   comparable conclusions, grounds, and limitations on the Issue and
   the applicable PR body/comment as well as chat; a link alone is insufficient.
   Progress updates may carry the new or corrected findings and identify the
   earlier retained results; final reports consolidate the current result.
   Shorten repeated process narration, not distinct findings or counterevidence.
5. On interruption or publication failure, write out the established portion and
   separate the unverified or unpublished portion with its reason and next
   owner/action. Retain the result for the existing publication route; never
   claim a destination was updated without that route's readback. A blocked
   destination does not erase results or justify withholding them from another
   authorized output.

## Choose the presentation

After structuring the facts and before drafting or revising the output, choose
its form by the relationship the reader needs to see. Honor explicit user and
destination format requirements. Structuring does not imply a table, list,
fixed headings, or the same layout for every destination.

| Information relationship | Suitable form |
| --- | --- |
| Compare multiple targets or map them across shared attributes | Table with meaningful row and column labels |
| Enumerate independent findings or actions with no meaningful order | Bulleted list |
| Show execution order, dependencies, or a meaningful sequence | Numbered list |
| Explain a conclusion, rationale, cause, context, or qualification | Prose |

Choose per section when relationships differ: a short conclusion, a comparison
table, and an explanation can coexist. Use prose for a single brief point; do
not fragment connected reasoning into bullets or invent a comparison axis to
justify a table. Keep cells concise and columns relevant. When long explanations,
sparse cells, or excessive width make a table harder to read, move explanations
to prose or use a list instead. Never omit evidence or qualifications to fit a
layout, and keep them visibly associated with the finding they support.

Before writeout, check that the form exposes the intended comparison or order,
reads clearly at the destination's width, and preserves the facts and limits
already structured. Change the form rather than distort the content. This is
part of the existing writing step, not a separate approval or validation gate.

## Ownership and engineering rationale

Supported sentences alone cannot detect a finding omitted before drafting.
Organizing existing facts first and checking coverage in both directions
addresses that omission; one internal owner keeps the output routes consistent.
Use existing records and source references rather than another summary store.

This skill neither selects tests nor authorizes reruns, environment discovery,
log resynchronization, new Issues, out-of-scope repairs, or extra completion
conditions. Publication authority, status, and remote readback stay with their
existing owners. Report an out-of-scope finding and its boundary without adding
its repair to the task. Raw log capture/storage and retention remain unchanged;
do not delay raw capture for narrative structuring or preserve artifacts that
their owner requires deleting. Preserve the finding's permitted disposition.

Keep credentials, private logs, and private reasoning out of public output.
Use authorized references and a safe factual summary; identify any withheld
evidence and resulting limitation without leaking it. The structured result
contains findings and explainable decision grounds, not raw transcripts or
private deliberation. This routine introduces no public skill, runtime shim,
CLI, schema, or mandatory separate report.
