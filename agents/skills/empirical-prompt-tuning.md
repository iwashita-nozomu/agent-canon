# empirical-prompt-tuning
<!--
@dependency-start
contract skill
responsibility Improves reusable agent instructions through fresh empirical evaluation and fixed-point iteration.
upstream design ./README.md shared public skill canon
upstream implementation ./catalog.yaml public skill identity, discovery, and commands
upstream implementation ./skill-dependencies.yaml prerequisites and routing relations
upstream design ../../documents/design/responsibility-rationale.md evidence-based instruction revision
upstream design ./research-workflow.md selection and final evaluation boundary
downstream implementation ../../tools/agent/skills/skill_shim_materializer.py generated runtime discovery shim
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py skill readback
@dependency-end
-->

## Purpose

Improve a reusable skill, slash command, task prompt, [AGENTS.md](../../AGENTS.md) section, or
code-generation prompt from observed task outcomes. When a behavior claim needs
fresh evidence, use an independent evaluator to exercise the changed instruction
and report what it did, what remained unclear, and which directions added work
without helping. Do not tune to one anecdote or treat a shorter prompt as an
improvement by itself.

## Use When

- the user requests evidence-based evaluation of a reusable instruction;
- repeated or consequential behavior suggests a reusable instruction defect; or
- a change needs observed behavior evidence before it can be accepted.

Do not require empirical evaluation for a one-off prompt or a routine edit with
no unresolved behavior claim. Style preference alone is not evidence of a
behavior change.

## Workflow

Start from the instruction's intended user, trigger, and observable outcome.
Use prior task results or feedback to identify a concrete behavior question;
separate a demonstrated miss from a hypothesis about its cause. If evaluation
will change the decision, choose representative scenarios that exercise the
affected behavior. Use an unused final evaluation set appropriate to a claim
about unseen tasks; otherwise limit the claim to the selected cases. Identify
the retained instruction and candidate separately, and define
the required outcome and unacceptable regressions before seeing fresh results.
Keep model, tools, inputs, and verification conditions comparable; record material
differences that limit attribution. Freeze the scenario and criteria, and give
the evaluator the target and dependencies it needs without supplying the expected
answer. For repeated selection and claims about unseen tasks, use
[Selection and Final Evaluation](research-workflow.md#selection-and-final-evaluation).

Use AgentCanon orchestration and `skill_evaluator` only when the selected
workflow activates empirical evaluation. The evaluator is fresh, read-only,
artifact-only, handles one scenario, and does not spawn agents. Select only the
runtime surfaces needed for that scenario. An unavailable required surface is
an explicit limit or failure; do not silently substitute another route.

Compare actual outputs with the selected criteria. Record observable omissions,
unnecessary actions, unclear instructions, discretionary assumptions, and
retries when they help explain the outcome. Record steps or duration only when
the runtime exposes them. Distinguish the evaluator's observation from the
author's interpretation; do not invent scores, timing, or proxies. When comparable
successful executions are available, contrast them with failures to identify
what must be preserved. If only failures are available, state that limit without
inventing a successful counterpart or requiring new runs just to form a pair.

For a supported instruction defect, make a local change to the underlying cause
and check nearby use cases at risk of regression. Preserve unrelated useful
guidance rather than regenerating the whole instruction. Remove guidance shown
to be irrelevant or counterproductive while preserving authority, safety, scope,
approval conditions, and completion requirements. Reject a candidate that widens
authority or bypasses approval regardless of its task score.

Promote a candidate only when comparable evidence meets the predefined outcome
and regression criteria. Fixing the known failure does not justify a regression
in a required nearby case. Keep the retained version after regression or
insufficient evidence; unchanged guidance is a valid result. Limit any adoption
to the scope supported by the evidence. Rerun only when a fresh result can
resolve the decision, and stop when the selected claim is supported or state
what remains unclear. A benchmark or improvement claim requires comparable
before-and-after observations; static format or consistency checks do not
establish improved model behavior. The
[revision rationale](../../documents/design/responsibility-rationale.md#evidence-based-instruction-revision)
explains this selection boundary.

## Scenario Packet

For the explicit `skill_evaluator` route, use the Scenario Packet owned by the
selected task-catalog entry and [Codex Subagents](../canonical/CODEX_SUBAGENTS.md).
For other evaluation, carry the target instruction, relevant dependencies,
scenario, selected outcome criteria, and runtime context in the existing task or
evaluation artifact. Use a durable artifact only for coordination or resumption.
This Skill adds no second field order, scoring scale, or packet schema. Keep
accepted findings separate from untested hypotheses.

## Reporting

Use the selected workflow's existing result format, including the explicit
`skill_evaluator` output contract when that route is active. Report the observed
result, criteria applied, ambiguity or extra work that affects the decision,
and limitations. In that existing record, retain parent and candidate revisions
or content hashes, the evidence used, and the adoption/rejection decision and
reason, so later revisions can reuse the actual history. A score change for
identical instruction bytes is execution variability, not an editing effect.
Do not create a second reporting grammar or rerun an otherwise
usable result only to repair formatting. The selected workflow owns scenario
definition, aggregation, accepted fixes, and the stop decision. The evaluator
does not edit files or replace missing runtime telemetry with guesses.
