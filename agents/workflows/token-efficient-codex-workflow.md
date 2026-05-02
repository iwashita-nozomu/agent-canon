<!--
@dependency-start
responsibility Documents token-efficient Codex workflow and agent modes.
upstream design ../canonical/CODEX_WORKFLOW.md Codex runtime workflow contract
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent routing contract
upstream implementation ../../.codex/config.toml defines token profiles
downstream design README.md workflow catalog references this overlay
@dependency-end
-->

# Token-Efficient Codex Workflow

This overlay keeps repo work rigorous while reducing unnecessary context,
subagent fan-out, and tool-output token load. Use it when the user asks to save
tokens, when a task is small, or when the current session is already long.

## Runtime Profiles

Use Codex profiles as parent-session modes:

- `token-lite`: narrow tasks, small docs edits, targeted diagnosis, and
  low-risk follow-up fixes.
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
- `spark-slice`: use `spark_worker` only for approved, design-traced, low-risk
  slices with fixed naming, write scope, and tests.
- `full-stage`: use the normal staged specialist set for requirements, plan,
  design, review, implementation, and closeout.
- `deep-review`: keep implementation local or in `worker`, but add independent
  read-only reviewers for architecture, correctness, evidence, and docs.

Mode selection rules:

- Start in `parent-direct` or `scout-only` for narrow diagnosis.
- Escalate to `spark-slice` only after design trace and reuse targets are fixed.
- Escalate to `full-stage` when a task touches multiple durable surfaces,
  introduces public names, changes workflow/config, or has open requirements.
- Escalate to `deep-review` when correctness, evidence, or architecture risk is
  higher than token cost.
- Do not spawn broad reviewer packs at intake. Use stage waves and close unused
  subagents before moving to the next stage.

## Context Budget Rules

- Read dependency headers and named upstream files before broad directory scans.
- Prefer `rg`, `sed -n`, `git diff --stat`, and MCP status tools over bulk
  file dumps.
- Summarize long artifacts into the run bundle before handing them to another
  agent.
- Pass file paths, clause IDs, and section names to subagents instead of chat
  summaries.
- Cap each subagent prompt to the packet it needs for the current stage; do not
  include all workflow docs in every handoff.
- Use `goal.md`, `team_manifest.yaml`, `schedule.md`, `work_log.md`, and
  `verification.txt` as durable memory instead of repeating long chat context.
- Use `tool_output_token_limit` profiles to keep large command output from
  flooding the session; rerun targeted commands when exact lines are needed.

## Escalation Triggers

Leave `token-lite` and move to `token-standard` or `token-deep` when any of
these happens:

- The fix surface crosses more than one package, workflow, or runtime surface.
- A new public API, config key, CLI flag, file path, or reusable helper is
  proposed.
- Existing implementation reuse is unclear.
- A reviewer returns `revise` or `escalate`.
- Validation fails for a reason not explained by the current design.
- `goal.loop_status` or `goal_loop.py status` says another iteration remains.

## Closeout

Token-efficient mode still requires the normal closeout evidence:

- dependency review for the full repo when required by `AGENTS.md`
- static analysis / CI appropriate to the task
- diff-check review when the task is repo-changing
- no unfinished planned work
- pushed commits when the task changes shared canon or template state

If token savings forced a narrower validation pass, record the omitted checks
and run the broader gate before user-facing completion.
