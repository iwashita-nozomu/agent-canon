# Reader-reproducible writing and verification results

<!--
@dependency-start
contract agent-runtime
responsibility Makes reader-facing writing reproducible and structures verification results without losing findings or re-owning publication.
upstream design ../../ROOT_AGENTS.md portable evidence and delivery boundary
upstream design ../skills/README.md internal skill visibility boundary
downstream design ../canonical/ROOT_DELIVERY.md general writing, chat, and handoff caller
downstream design ../skills/report-writing.md report drafting caller
downstream design ../skills/pr-processing.md Issue and PR publication caller
downstream design github-connected-work.md connected publication caller
downstream design README.md internal routine index
@dependency-end
-->

## Invocation and boundary

Use this internal routine before drafting, updating, posting, or saving any
reader-facing writing: chat, Issue/PR bodies and comments, reports, README and
operational documentation, designs, specifications, plans, instructions, reviews,
code comments, and handoffs. Verification results are one case, not the activation
condition. Proposed or unrun work still needs understandable prerequisites,
steps, and success criteria; it must not be represented as an observed result.

Apply [reader reconstruction](#reader-reconstruction) to the content being written.
For verification findings, also use [Structure before writeout](#structure-before-writeout),
including progress, interrupted, and failed work; do not wait for all verification
to finish. A brief acknowledgement needs no invented procedure or evidence fields.

Reuse the applicable source and existing task/Issue record rather than creating
another summary store. Reconcile new facts and corrections before the next output.
This is a writing step, not a new approval, checker, ledger, or fixed template.
Optional document topology planning does not make the applicable steps optional.

| Caller | Output boundary |
| --- | --- |
| [Evidence and delivery](../canonical/ROOT_DELIVERY.md#reader-facing-writing) | General writing, chat progress, final result, and handoff |
| [Report writing](../skills/report-writing.md#procedure) | Every report draft or revision, including proposals and procedures |
| [PR processing](../skills/pr-processing.md#publication-boundary) | Every Issue/PR body or comment |
| [Connected work](github-connected-work.md#use-and-boundary) | The same outputs through authorized GitHub tools |

## Reader reconstruction

Write for an intended reader who has the output and its explicitly identified,
accessible references, but not the author's chat history, temporary workspace,
or unstated assumptions. Before writeout, walk through what that reader needs
to repeat the relevant action, apply the instruction, or check the conclusion.
Supply the applicable relationships below, not empty headings or a universal form.

| Reader need | Information to preserve |
| --- | --- |
| Identify the subject and applicability | Purpose, scope, target and precise locator; revision or snapshot when the claim depends on it |
| Establish the starting conditions | Relevant prerequisites, input values or durable retrieval/creation steps, configuration, and environment differences that affect the outcome |
| Repeat the procedure | Ordered actions through the owner's fixed route; exact commands/arguments, working directory, input paths, and branch conditions when needed |
| Recognize the result | Expected behavior or success criterion, separately from observed output, error, exit status, and where that evidence can be inspected |
| Reconstruct an explanation or decision | Definitions, premises, sources, method or derivation, and the evidence-to-conclusion relationship with assumptions and limitations |

Use precise file/symbol/section or artifact locators; use immutable references for
snapshot-specific observations. A source link supports the explanation rather
than replacing it. Reuse an existing procedure by identifying its applicable
section and the task-specific inputs or differences; do not copy an entire manual.
Generic examples may use variables only when their meaning and how to obtain or
choose values are explained. Ellipses, unexplained placeholders, "as before",
"the usual command", or author-only paths cannot stand in for necessary steps.

Retain known outcome-relevant versions, seeds, tolerances, units, aggregation rules,
and nondeterministic limits when applicable, not a speculative environment dump.
For a non-executable design or explanation, reconstructability concerns its
premises and method, not a fabricated command or test. Do not disclose private
reasoning; give the factual justification needed to evaluate the conclusion.

Fill missing context from already available evidence. When a required input,
permission, or result is unknown, unavailable, or private, state the specific gap,
its effect on reproduction or interpretation, and any feasible next owner/action.
Use a safe fixture or authorized reference only when it exists, and explain any
loss of equivalence; never invent original inputs or claim an unrun procedure
was reproduced. Do not add reruns, environment discovery, or evidence retention
contrary to the existing execution, publication, or storage owner.

Finally, check that the reader can follow the relevant chain without guessing.
Repair the missing explanation or narrow the claim explicitly; a polished layout,
shortness, or a citation count does not establish sufficiency. Scale detail to the
reader's task. Progress may identify a specific retained record for unchanged
conditions, but an independently consumed document or handoff must resolve its
necessary context without reconstructing a private conversation.

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

After structuring the content and before drafting or revising the output, choose
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

Evidence-backed sentences can still omit the inputs, steps, or premises needed
by another reader. Reader reconstruction addresses that gap for all writing;
verification-specific structuring additionally prevents lost findings and
counterevidence. One internal owner keeps the output routes consistent, while
the common root remains self-contained for source-free consumers. The existing
file path is retained; this is not a second writing or reproduction workflow.

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
