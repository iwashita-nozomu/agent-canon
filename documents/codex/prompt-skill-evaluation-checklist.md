<!--
@dependency-start
contract reference
responsibility Defines checklist and manifest format for skill, prompt, and workflow behavior evals.
upstream design ../../agents/canonical/skills.md defines skill registry.
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md defines subagent routing.
upstream design ../../.agents/skills/code-visualization/SKILL.md defines the runtime route under evaluation.
upstream design ../../agents/skills/code-visualization.md defines the canonical route contract under evaluation.
downstream implementation ../../evidence/agent-evals/issue_eval_manifest.toml registers issue-derived eval cases.
downstream implementation ../../.github/ISSUE_TEMPLATE/eval-capture.yml captures new eval candidates.
downstream implementation ../../.github/PULL_REQUEST_TEMPLATE.md requires eval evidence.
@dependency-end
-->

# Prompt And Skill Evaluation Checklist

Use this checklist when changing skills, subagent prompts, workflow prose, hook
messages, task routing, or closeout rules.

## Required Checks

1. Activation
   - The skill/subagent/tool activates for tasks that need it.
   - It stays quiet for tasks that do not need it.
1. Responsibility boundary
   - The role does not implement while acting as reviewer/designer/researcher.
   - Helper, public API, first-party library, workflow, and shared-canon changes
     require task authority.
1. Evidence and closeout
   - Required tool/check evidence is named.
   - Missing evidence is marked not applicable only with a reason.
1. Regression capture
   - The PR adds or updates an eval case, or states why the change is not evalable.

## Failure Taxonomy

- `scope-creep`: work expands beyond the user request.
- `helper-sprawl`: helper or wrapper code is added before owner/API evidence.
- `upstream-mutation`: vendor, external, or shared library is changed without authority.
- `api-surface-miss`: public API, exports, config, or examples were not traversed.
- `responsibility-boundary`: repo/module/document ownership was misread.
- `workflow-bypass`: defined skill, workflow, or tool route was skipped.
- `doc-drift`: stale, duplicate, or conflicting docs were left visible.
- `insufficient-evidence`: conclusion is not backed by required evidence.
- `wrong-artifact`: output format/path does not match the request.
- `non-reproducible-review`: review finding was not turned into a test or eval.

## Manifest Format

Issue-derived evals are registered in
`evidence/agent-evals/issue_eval_manifest.toml`. Each row records category, source
issue, protected behavior, expected route, forbidden route, oracle type, and
linked rule/tool/workflow.

Close an agent-behavior issue only after the eval is added, or after the issue
body/PR body records why an eval would not be meaningful.

## Empirical Scenario Protocol

The parent owns empirical skill evaluation. Parent Iteration 0 freezes two
answer-free Scenario Packets: canonical-graph `full` and `changed`. Every
packet must include the full Prompt Under Test
text and path, Canonical Target Files, Prompt Dependency Files, the frozen
scenario, the requirements/checklist, the method, and the fixed report grammar.
It must not include an expected command, expected artifacts, an answer, prior
evaluator reasoning, or a prior result.

The evaluator read allowlist is limited to the packet-listed Evaluation Skill,
Prompt Under Test, Canonical Target Files, Prompt Dependency Files, and test
documentation. A fresh evaluator receives one scenario only, with a unique
instance ID, iteration ID, and packet digest. No evaluator instance is reused
across scenarios, iterations, or malformed-report reruns. The evaluator is
read-only, does not call nested agents, and does not become the renderer,
checker, scanner, or implementation agent.

## Observed Report Grammar

The evaluator returns only the following ordered sections and fields:

```text
Output:
command=<exact proposed command or none>
artifacts=<comma-separated exact basenames or none>
authority=<owner statement>
route=<selected route>
Requirement Results:
R<integer>=<pass|fail|malformed>: <short evidence>
Telemetry:
retry_count=<integer>
ambiguity=<none|token>
extra_refs=<comma-separated extra references or none>
Result Metadata:
scenario_id=<id>
iteration=<integer>
provenance=fresh
Evaluation Status:
evaluation_status=<pass|fail>
feedback_actions_resolved=no
learning_capture_complete=no
```

The four `Output` keys are observed behavior, not an embedded answer. Every
listed fixed field is mandatory exactly once: `command`, `artifacts`,
`authority`, `route`, `retry_count`, `ambiguity`, `extra_refs`, `scenario_id`,
`iteration`, and `provenance`; the three `Evaluation Status` fields are also
mandatory exactly once. `evaluation_status` is the fresh evaluator's observed
status for that report. It is not the parent's score, critical-pass decision,
convergence result, or final completion state. Missing or duplicated fields,
reordered or
duplicated headings, missing or duplicated packet-listed requirement IDs,
unknown requirement IDs, invalid enum/value tokens, a `scenario_id` or
`iteration` that differs from the packet, provenance other than `fresh`, or
free text outside the four sections make the report malformed. The Scenario
Packet defines the allowed integer requirement IDs; the evaluator reports each
packet-listed ID exactly once and does not hard-code any fixed ID set. A
malformed report is unscored and is rerun with a new fresh evaluator on the
same frozen packet.

## Parent Scoring And Convergence

After each return, the parent scores the observed `Output` and requirement
observations against this frozen checklist. The `Evaluation Status` section is
the fresh evaluator's observed report status only; it does not score the skill
and does not finalize the evaluation. The parent artifact owns the fields
`parent_score_percent=<0..100>` and `parent_critical_pass=<yes|no>`; those
fields are derived by the parent and cannot be supplied as parent decisions by
the evaluator. The parent also owns iteration convergence and final completion;
neither is implied by `evaluation_status=pass`. The route requirements are:

- `full` uses exactly `python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json`.
- `changed` uses exactly `python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json`, and only when changed scope is explicit.
- `--json` is invalid. The canonical graph owns dependency status and facts.
  The renderer performs one typed query and owns the six projections; no
  supplied-input or parser fallback exists.
- The bundle contains exactly `dependency_graph.tsv`,
  `dependency_graph.ir.json`, `dependency_graph.md`, `dependency_graph.dot`,
  `dependency_graph.html`, and `manifest.json`.
- This route does not select a separate raw checker, scan, helper, or Mermaid
  route.

An iteration converges only when all three scenarios have valid reports,
parent-passing requirements, `ambiguity=none`, and the exact route checks pass.
Completion requires two consecutive converged iterations with matching
per-scenario retry counts, zero retries, and a hold-out gap strictly below 15
percentage points in both iterations. The parent records packet digest, raw
report, parsed requirement results, score, retry count, ambiguity, provenance,
and convergence decision. The parent artifact records
`parent_score_percent`, `parent_critical_pass`, and the convergence decision.
`repo-wide-test-inventory=absent` is a separate
structural finding and is not replaced by this focused checklist.
