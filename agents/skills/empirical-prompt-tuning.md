# empirical-prompt-tuning
<!--
@dependency-start
contract skill
responsibility Improves reusable agent instructions through fresh empirical evaluation and fixed-point iteration.
upstream design ./README.md shared public skill canon
upstream implementation ./catalog.yaml public skill identity, discovery, and commands
upstream implementation ./skill-dependencies.yaml prerequisites and routing relations
downstream implementation ../../tools/agent/skills/skill_shim_materializer.py generated runtime discovery shim
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py skill readback
@dependency-end
-->

## Purpose

Improve a reusable skill, slash command, task prompt, `AGENTS.md` section, or
code-generation prompt by having an independent evaluator execute the
instruction surface and report both observable behavior and its own reading
experience. Stop only when the frozen scenarios have converged.

## Use When

- a reusable instruction is new or substantially revised;
- an agent's failure may be caused by ambiguity in the instruction; or
- a high-value instruction needs evidence of robust behavior.

Do not use this for a one-off prompt or for changes based only on the author's
stylistic preference.

## Workflow

1. **Iteration 0 (parent-owned static gate).** Check that the description's
   triggers and purpose match the body. Record unresolved references,
   contradictions, undefined fields, stale paths, and report-grammar defects.
2. **Freeze the evaluation packet.** Define two or three scenarios: at least
   one representative `baseline` and one `hold-out`. For each, freeze a
   three-to-seven-item checklist with at least one `[critical]` requirement,
   scoring rules, observability rules, and the exact reporting grammar before
   any result is seen. Give the evaluator enough target/dependency context to
   decide without exploratory file searches, but do not give it an expected
   answer or suspected defect.
3. **Select the evaluator route.** Use AgentCanon orchestration and its
   `skill_evaluator` role only when the selected workflow explicitly enables
   empirical skill evaluation. The evaluator is fresh, read-only,
   artifact-only, and handles one scenario; it does not spawn nested agents.
   Preflight only the surfaces selected by that packet. An unavailable required
   surface is an explicit failure, not a silent downgrade.
4. **Collect both sides of the result.** The fixed report records requirement
   status (`○`, `部分的`, or `×`), with success requiring every `[critical]`
   requirement to be `○`, and accuracy as `○=1`, `部分的=0.5`, `×=0`.
   Also record the evaluator's unclear points, discretionary completions,
   extra references, and retries. Record `steps` and `duration` only when the
   runtime exposes them; otherwise use
   `n/a(runtime hidden/unavailable)` rather than inventing values.
5. **Debug and rerun.** For a failed or partial result, perform static
   analysis, fix one accepted issue theme, and rerun the same frozen packet
   with a new evaluator. Do not weaken the scenario or checklist to fit a
   result. Keep qualitative ambiguity and discretionary completion primary;
   use accuracy, retries, extra references, and visible runtime metrics as
   supporting quantitative evidence.
6. **Convergence.** Treat a run as converged only when all frozen scenarios
   pass, new ambiguity is zero, accuracy is stable (within three percentage
   points), and the visible metrics or fallback proxies are stable. Hold-out
   accuracy is compared separately and must remain within 15 percentage points
   of the baseline average. Require two consecutive converged iterations.

## Scenario Packet

Use stable fields in this order:

`Evaluation Mode`, `Iteration ID / Scenario ID`, `Scenario Class`, `Evaluation
Skill`, `Prompt Under Test`, `Canonical Target Files`, `Prompt Dependency
Files`, `Scenario`, `Checklist`, `Scoring Rules`, `Reporting Contract`, and
`Observability Contract`.

When the selected orchestration route requires it, also include evaluator
provenance, a packet boundary, static-analysis commands, and the selected
runtime-surface preflight. Keep prior accepted changes separate from
unaccepted hypotheses.

## Fixed Report

The evaluator returns exactly this structure; a malformed report is unscored
and rerun with a fresh evaluator:

```text
- Output:
- Requirement Results:
  - [critical|noncritical] <requirement id> | status=<○|部分的|×> | reason=<1 line>
- Unclear Points:
- Discretionary Completions:
- Extra References: count=<N>; items=<comma-separated list or none>
- Retries: <integer>
```

The parent owns scenario freezing, aggregation, accepted fixes, and the
convergence decision. The evaluator does not silently edit files or replace
missing runtime telemetry with guesses.
