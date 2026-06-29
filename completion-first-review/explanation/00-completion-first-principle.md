# Completion-First Principle
<!--
@dependency-start
contract reference
responsibility Explains why completion judgment rules must precede agent settings and workflow changes.
upstream design ../README.md completion-first review index
upstream design ../../AGENTS.md AgentCanon repository instructions
upstream design ../../ROOT_AGENTS.md shared runtime entrypoint
upstream implementation ../../tools/agent_tools/task_close.py current closeout evaluator
@dependency-end
-->

## Reader Map

Use this document to answer why completion judgment must precede agent settings,
workflow changes, prompt evals, MCP routing, and self-growth loops. Read Core
correction and Revised priority order first, then use the P-1, manual unlock,
evidence hierarchy, Definition of Done, runtime-configuration, self-growth, and
invariant sections to trace the completion-first argument.

## Core correction

The first priority is not agent settings. The first priority is the set of rules and tools that decide whether a task is complete.

Agent settings, tool routing, MCP configuration, skill selection, workflow contracts, PR checklists, and self-growth loops all depend on the answer to one earlier question:

> What counts as done, and who or what is allowed to say it is done?

If this question is not answered first, every other improvement can become decorative. A workflow can require review, but a task may still close with a hand-written `user_completion_report=unlocked`. A skill can say to run prompt evals, but closeout may not check that the same eval was rerun. A tool can emit a pass token, but no command-backed evidence may exist. MCP can be unavailable, but a preset behavior token may still claim MCP passed.

The completion system must therefore be treated as the root layer of AgentCanon.

## Revised priority order

The corrected order is:

1. **P-1: Completion judgment rules and completion-verifier tooling**
2. P0: Agent settings and runtime invariants
3. P1: Tool, evidence, and verifier implementation
4. P2: MCP, goal loop, and alternate route evidence
5. P3: Self-growth state machine
6. P4: Surface ownership, AgentCanon sync, and submodule pin discipline
7. P5: Workflow and skill contracts
8. P6: Template bootstrap, Docker, CI, and PR evidence
9. P7: Research, experiment, claim, and long-form documentation rigor
10. P8: Audit, metrics, and retirement

This order is not cosmetic. It changes the architecture. Everything below P-1 is required to serve the completion definition.

## What P-1 must define

P-1 must answer these questions before any runtime or workflow tuning is considered complete:

- Which task profiles exist?
- Which profile applies to this task?
- Which artifacts are required for that profile?
- Which commands or validators are required?
- Which evidence is accepted?
- Which evidence is explicitly not accepted?
- Which reviewer independence conditions are required?
- Which MCP states are acceptable?
- Which alternate route states are acceptable?
- Which self-growth repair states are acceptable?
- Which tool decides final completion?
- Which report is allowed to be user-facing?

In practical terms, P-1 means adding or formalizing the following surfaces:

- `agents/canonical/DEFINITION_OF_DONE.md`
- `agents/canonical/closeout_profiles.yaml`
- `tools/agent_tools/completion_verifier.py`
- `agents/templates/artifact_schema.yaml`
- `agents/templates/behavior_event.schema.yaml`
- `agents/templates/validation_evidence.schema.yaml`
- `evidence/agent-evals/negative_cases/`
- generated `completion_verification_report.json`
- generated `completion_report.md`

## Why manual unlock must not be authoritative

Current closeout artifacts can contain status-like fields such as `user_completion_report=unlocked` or `validation_complete=yes`. Those fields are useful as human-readable summaries, but they should not be the authority. If a text file can be edited by the same actor who wants to finish the task, it cannot be the final authority for completion.

The authority should be a verifier chain:

```text
request profile -> required evidence -> verifier execution -> verdict -> generated completion report
```

A human or agent may explain the result, but the pass/fail decision should come from a tool that reads evidence and returns an exit code.

## Completion evidence hierarchy

The completion system should distinguish evidence quality.

Lowest trust:

- checkbox checked by hand,
- pass token typed into Markdown,
- pasted command output without command metadata,
- vague reviewer approval with no diff ref,
- statement that MCP passed without MCP or alternate route artifact.

Medium trust:

- structured artifact with required fields,
- reviewer artifact with finding IDs,
- command output linked to a command name and timestamp.

High trust:

- command-backed evidence with command, cwd, runtime profile, timestamps, exit code, stdout/stderr hashes,
- schema-valid behavior event with evidence path,
- independent review tied to exact diff ref,
- replay fixture that fails before repair and passes after repair,
- completion verifier report produced from profile requirements.

Completion should require high-trust evidence for strict, self-growth, and release profiles.

## Definition of Done should be profile-based

A single Definition of Done is too coarse. The repo needs profile-based completion.

Suggested profiles:

```yaml
profiles:
  advisory:
    purpose: No repo change. Provides guidance only.
    rejects:
      - fake validation evidence
      - fake commit/push evidence

  trivial:
    purpose: Very small low-risk repo change.
    requires:
      - request clause resolution
      - changed file summary
      - targeted validation or explicit not-applicable reason

  standard:
    purpose: Normal repo-changing task.
    requires:
      - routing decision
      - schedule
      - work log
      - validation evidence
      - closeout gate
      - artifact schema validation

  strict:
    purpose: Shared canon, CI, Docker, runtime, public workflow, or high-risk change.
    extends: standard
    requires:
      - surface classification
      - dependency review
      - static analysis
      - independent diff-check
      - review finding lifecycle
      - commit/push evidence

  self_growth:
    purpose: Changes to agent behavior, skill, workflow, eval, memory, or tool gates.
    extends: strict
    requires:
      - self-growth repair manifest
      - learning diagnosis
      - negative fixture
      - positive replay
      - prompt/workflow eval report
      - behavior eval report
      - promotion or retirement decision

  release:
    purpose: Template release, AgentCanon pin update, GitHub Actions, or PR surface change.
    extends: strict
    requires:
      - remote status
      - submodule pin evidence
      - fresh clone evidence
      - PR evidence matrix
```

## Completion is the parent of runtime configuration

Once profiles exist, agent settings can be evaluated against them.

Examples:

- If profile is `self_growth`, runtime must support replay and eval evidence.
- If profile is `strict`, reviewer independence is mandatory.
- If profile is `release`, fresh clone evidence is mandatory.
- If profile is `advisory`, repo validation evidence should not be fabricated.
- If profile requires MCP, MCP pass or accepted alternate route must be recorded.

This means runtime configuration should not decide completion. Runtime configuration should satisfy completion.

## Completion-first effect on self-growth

Self-growth is especially vulnerable to false completion. It is easy to say that the agent learned something by adding a line to memory or prompt docs. That is not enough.

For self-growth, completion should require:

1. observed feedback,
2. diagnosis of root cause,
3. repair surface decision,
4. changed surface evidence,
5. eval rerun,
6. replay case,
7. promotion or no-promotion decision,
8. retirement or review-after policy.

Without a completion-first design, self-growth becomes memory accumulation. With completion-first design, self-growth becomes a regression-tested repair loop.

## Completion-first invariant

The central invariant is:

```text
No user-facing completion report may be emitted unless the selected closeout profile has passed through verifier-produced evidence.
```

Everything else in this review follows from that invariant.
