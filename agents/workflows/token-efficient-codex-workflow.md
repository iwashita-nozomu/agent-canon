<!--
@dependency-start
contract workflow
responsibility Documents token-efficient Codex workflow and agent modes.
upstream design ../canonical/CODEX_WORKFLOW.md Codex runtime workflow contract
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent routing contract
upstream implementation ../../.codex/config.toml defines shared runtime limits
downstream design README.md workflow catalog references this overlay
@dependency-end
-->

# Token-Efficient Codex Workflow

This overlay keeps repo work rigorous while measuring subagent fan-out and
tool-output token load. Use it when the user asks to save tokens, when a task has
a boundary-evidenced route, or when the current session is already long. Context
construction is owned by `agents/COMMUNICATION_PROTOCOL.md`; this overlay never
shrinks requested context. It chooses when to load, reference, or hand off
already-owned context artifacts.

Token reduction is treated as a measurable claim: compare a baseline session footprint
against the candidate slice, record the ratio, and keep only the changes that preserve
skill accuracy while cutting total tokens by at least half for the same eval envelope.
The first lever is matching reasoning effort to owner-boundary evidence and role
responsibility; only after that should broader profile changes or output caps be
considered.

## Reader Map

- This overlay owns token-saving modes, fan-out choices, reduction evidence, escalation triggers, and closeout constraints for Codex repo work.
- The early sections define runtime profiles and agent modes; the middle sections point back to the context protocol and define token reduction evidence; the final sections define escalation and closeout.
- Use `## Runtime Profiles` and `## Agent Modes` before changing subagent fan-out or tool-output limits.
- For chunked reading, keep the active mode and evidence target in view, then open only the protocol, reduction, escalation, or closeout section needed by the current task phase.

## Runtime Profiles

Use Codex profiles as parent-session modes. For current Codex CLI behavior,
define these profiles in user-level config (`~/.codex/config.toml` or
`$CODEX_HOME/config.toml`), not in the project-local `.codex/config.toml`.

- `token-lite`: boundary-evidenced tasks, targeted diagnosis, and low-risk
  follow-up fixes.
- `token-standard`: normal repo work that still needs staged gates, review, and
  validation.
- `token-deep`: architecture, broad refactor, research synthesis, ambiguous
  requirements, or high-risk review.

Preferred launch forms:

```bash
codex -p token-lite
codex -p token-standard
codex -p token-deep
```

Do not use `token-lite` to bypass required review, dependency analysis,
validation, or closeout gates; token-lite does not relax those gates. It only
changes how much context and fan-out are loaded at once.

## Agent Modes

Select one mode before spawning subagents:

- `parent-direct`: parent handles trivial or mechanical work without subagents.
  Record why no subagent is needed.
- `scout-only`: spawn read-only `explorer` or reviewer agents to answer bounded
  questions while parent keeps the critical path.
- `spark-slice`: use `spark_worker` only for approved low-risk slices derived from the Abstract Design Frame and design trace, with fixed naming, write scope, and tests.
- `full-stage`: use the normal staged specialist set for requirements, plan,
  design, review, implementation, and closeout.
- `deep-review`: keep implementation local or in `worker`, but add independent
  read-only reviewers for architecture, correctness, evidence, and docs.

Mode selection rules:

- Start in `parent-direct` or `scout-only` for bounded diagnosis with a recorded
  owner boundary.
- Escalate to `spark-slice` only after the Abstract Design Frame, design trace, and reuse targets are fixed.
- Escalate to `full-stage` when a task touches multiple durable surfaces,
  introduces public names, changes workflow/config, or has open requirements.
- Escalate to `deep-review` when correctness, evidence, or architecture risk is
  higher than token cost.
- Do not spawn broad reviewer packs at intake. Use stage waves and close unused
  subagents before moving to the next stage.
- `parent-direct` is not a loophole for goal-driven repo work that requires
  pre-goal review. If explicit spawn authorization is absent, the token-efficient
  path is to prepare the bounded fan-out plan and request or wait for
  authorization, not to treat the parent-only result as equivalent review.
- If a higher-priority runtime blocks implicit spawn, record
  `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` or `SUBAGENT_AUTHORIZATION=required`
  in the run artifact and keep the parent slice tied to the requested scope and
  owner boundary. Token efficiency does
  not permit fabricating specialist review evidence.

## Context Protocol Use

- Follow `agents/COMMUNICATION_PROTOCOL.md` for context visibility, repository
  investigation packets, parent-direct notes, and fresh subagent capsules.
- For tool-covered questions, call the canonical checker, router, semantic
  index, dashboard, or structured report before prose review or subagent
  handoff. Treat pass/finding output as the authority for that covered property.
- Read exact owner paths, dependency headers, and named upstream files after a
  tool artifact or protocol packet identifies the needed context.
- Hand structured tool artifacts to subagents through path references in the
  protocol-owned capsule; do not ask them to re-run deterministic checks by
  reading the same documents.
- Store long raw outputs in the run bundle and pass their artifact paths,
  clause IDs, and section names instead of chat summaries.
- Use `tool_output_token_limit` profiles to keep command output reviewable;
  rerun targeted commands when exact lines are needed.
- If a canonical tool lacks the abstraction needed for routing, extend the tool
  or record the tool-contract gap instead of compensating with broad manual
  reading.

## Token Reduction Protocol

- Capture a baseline Codex session footprint before changing prompts or
  workflows.
- Capture a candidate footprint after the change using the same skill / workflow
  eval envelope.
- Compare the two with `tools/agent_tools/compare_codex_token_footprints.py`.
- Record the baseline session, candidate session, total tokens, and token ratio
  in `workflow_monitoring.md`.
- Treat `token_ratio <= 0.5` as the target, but do not accept the reduction if
  the relevant prompt or behavior eval regresses.
- If a reduction removes context needed for the requested scope, reject it and
  continue until the skill or behavior evals still pass for the same surface.

## Escalation Triggers

Leave `token-lite` and move to `token-standard` or `token-deep` when any of
these happens:

- The fix surface crosses more than one package, workflow, or runtime surface.
- A new public API, config key, CLI flag, file path, or reusable helper is
  proposed.
- Existing implementation reuse is unclear.
- A reviewer returns `revise` or `escalate`.
- Validation fails for a reason not explained by the current design.
- `goal_loop.py status` says another iteration remains.

## Closeout

Token-efficient mode still requires the normal closeout evidence:

- dependency review for the full repo when required by `AGENTS.md`
- static analysis / CI appropriate to the task
- diff-check review when the task is repo-changing
- no unfinished planned work
- pushed commits when the task changes shared canon or template state

If token savings forced a bounded validation pass, record the omitted checks and
run the broader gate before user-facing completion.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
