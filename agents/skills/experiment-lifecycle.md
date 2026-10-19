# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Owns experiment run identity, lifecycle state, reproducibility core, and explicit rerun/publication decisions without owning artifact files or report prose.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
downstream implementation ../../tools/validation/semantic/tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
@dependency-end
-->

## Purpose

Carry an experiment from its question through execution and interpretation. Use
the caller's runner, project environment, inputs, and comparison; record enough
source/config/command identity and terminal status to explain the observed
result. Artifact writing, report prose, and retention decisions stay with their
selected owners.

## Use When

Use when the request includes planning, running, interpreting, or rerunning an
experiment. Topic creation, GPU diagnosis, report generation, and code/archive
closeout are separate conditional tasks.

## Method

1. State the question or claim, the inputs and comparison that can answer it,
   and the stopping condition needed for this request.
2. Run through the project's existing runner and environment. Preserve their
   configured defaults and execution semantics; use a specialized profile or
   variant only when the requested evidence needs it.
   For numerical experiments, follow [Before optional changes](computational-optimization.md#before-optional-changes):
   obtain or reuse the agreed method's baseline before optional tweaks, preserving
   required method components and current execution authority.
3. Observe the actual terminal result. Distinguish completed, failed, and
   partial work, and keep source/config/command details needed to reproduce or
   interpret that result. A partial or failed run does not establish a completed
   comparison.
4. Rerun only when the question or supported cause requires another run. Keep
   changed inputs or execution conditions identifiable; report what changed and
   what the comparison can establish.
5. Use an existing artifact or report owner when the requested outcome needs
   durable raw results, archive handling, or reader-facing claims. Do not turn
   an ordinary run into an archive or report workflow.

## Topic Preparation

When topic setup is part of the request, use the caller's existing creator or
scaffold. For an AgentCanon experiment topic, its native creator is
`python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>`; select
supported options only when the topic's actual needs call for them.

## Topic boundary

Follow the project's existing separation between experiment orchestration,
per-case logic, runtime lifecycle, and artifact/report handling. Let the topic
owner define its file layout and run contract; do not impose AgentCanon
filenames or a wrapper on another project.

For execution, prefer the caller's established runner. When AgentCanon's
managed formal or verified route is selected, its existing invocation is:

```bash
python3 -m tools.experiments.execution.run_managed_experiment \
  --topic <topic> --variant <variant> -- <project run command>
```

## Conditional owner routes

- GPU execution or crash diagnosis: use [gpu-execution](gpu-execution.md) and
  the project-selected runner when those concerns affect the requested run.
- Result identity, checksum, or durable writeout: use
  [result-artifact-writeout](result-artifact-writeout.md) when the result must
  be retained or shared. Use [report-writing](report-writing.md) only when a
  reader-facing report is requested.
- Multiple research iterations, backlog tracking, or a separate topic review:
  use [research-workflow](research-workflow.md),
  [adaptive-improvement-loop](adaptive-improvement-loop.md), or
  [experiment-review](experiment-review.md) only when that work is selected.
- Retiring AgentCanon topic code: apply the existing
  [topic branch scope](../../documents/operations/BRANCH_SCOPE.md#experiment-topic-branch-scope)
  and [archive and summary policy](../../documents/experiments/result-log-retention-and-visualization.md#experiment-archive-and-summary-retention).
  That policy requires retrievable retained evidence before retirement and
  preserves shared models/helpers, execution/regression infrastructure, and
  completed summaries on `main`; list exact summaries missing from `main` in
  the target Issue. This closeout route does not apply to every run or retention
  plan.
