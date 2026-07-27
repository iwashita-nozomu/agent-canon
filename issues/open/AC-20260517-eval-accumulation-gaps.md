# Eval Accumulation Gaps

<!--
@dependency-start
contract issue
responsibility Records the finding that eval and hook evidence accumulation needs a dedicated gate.
upstream design ../../evidence/agent-evals/README.md defines eval usage requirements.
upstream design ../../documents/runtime-log-archive.md defines append-only eval and hook result storage.
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated eval evidence.
downstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py consumes accumulated evidence.
@dependency-end
-->

issue_id: AC-20260517-eval-accumulation-gaps
status: in_progress
source: user
severity: S1
evidence: User feedback on 2026-05-17: eval collection is still not reliably accumulating into AgentCanon.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/242
affected_surfaces: evidence/agent-evals/README.md, documents/runtime-log-archive.md, .codex/hooks/hook_event_log.py, .codex/hooks/skill_usage_logger.py, tools/agent_tools/evaluate_skill_workflow_prompts.py, tools/agent_tools/generate_agent_improvement_guide.py, tools/agent_tools/generate_agent_runtime_dashboard.py
edit_scope: tools/agent_tools/eval_accumulation_check.py, tests/agent_tools/test_eval_accumulation_check.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, tools/ci/run_all_checks.sh, .github/workflows/agent-canon-static-gates.yml
required_action: Add a gate that verifies AgentCanon-owned hook and skill eval result directories are append-only, tracked, and structurally readable.
close_condition: The gate passes on current accumulated evidence and fails on missing result directories, duplicate hook run ids, malformed JSONL, or ignored result paths.

## Reader Map

- Owns the open issue record for missing mechanical eval/hook accumulation
  gates.
- Main path: Finding, Required Fix, dated dashboard/routing evidence, and
  triage notes.
- Read this before implementing or reviewing eval accumulation checker and
  static-gate work.
- Boundary: the issue records required repair and evidence; implementation
  authority remains with the affected tool, test, catalog, and CI paths.

## Finding

Hook and skill eval logs are now present, but there is no single checker that
proves they are landing in the AgentCanon-owned result tree and remain readable
by improvement tooling. This leaves the system dependent on convention rather
than a mechanical accumulation contract.

## Required Fix

Add an eval accumulation checker and wire it into static gates. The checker
should stay structural: it must not reject old evidence merely because it is
legacy-shaped, but it must fail on missing canonical directories, ignored
result paths, malformed JSONL, duplicate ids, or missing required fields in new
namespaced hook logs.

## 2026-05-17 Dashboard Evidence

The Agent Runtime Dashboard now routes missing evidence back to this issue
instead of only showing raw counts. The latest observed dashboard run exposed:

```text
AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=832
AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_ATTRIBUTED=29
AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING=803
AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS=0
AGENT_RUNTIME_DASHBOARD_PROMPT_ENTRIES=0
AGENT_RUNTIME_DASHBOARD_TOOL_SELECTION_ENTRIES=756
```

This confirms that structural accumulation exists, but the log schema still
needs better workflow attribution, prompt capture coverage after deployment,
and token footprint comparison evidence.

## 2026-05-21 Routing Cutover Evidence

Accumulated skill routing logs remain append-only after routing prompt repairs,
but current gap analysis now cuts over at the latest Git commit for the
affected skill source paths. This prevents already-fixed skill routing misses
from staying in the active `Skill Routing Gaps` backlog while preserving the raw
JSONL chronology for audit and repeated-failure analysis.

## 2026-05-21 Remaining Skill Routing Repair

The remaining `md-style-check` and `agent-learning` gaps need explicit
selection, not candidate promotion. Candidate-only keyword matches stay
candidate evidence. Plain public skill ids in a user prompt now count as
selected skill evidence, and `$agent-orchestration` now routes Markdown
lint/link/heading work to `md-style-check` and agent-behavior feedback,
recurrence prevention, and retrospectives to `agent-learning`.

## 2026-06-07 Triage

This issue remains open after stale-issue triage. The current integration
branch moves eval source manifests to `evidence/agent-evals/`, keeps
`agents/evals/` as a legacy resolver, and updates accumulation-aware tools and
tests. The residual close condition is not only source-manifest placement:
dashboard workflow attribution, prompt capture coverage, and token-footprint
comparison evidence still need a branch that proves the accumulated archive is
complete enough for improvement tooling.
