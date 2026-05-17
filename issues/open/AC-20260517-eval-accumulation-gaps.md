# Eval Accumulation Gaps

<!--
@dependency-start
responsibility Records the finding that eval and hook evidence accumulation needs a dedicated gate.
upstream design ../../agents/evals/README.md defines eval usage requirements.
upstream design ../../agents/evals/results/README.md defines append-only eval result storage.
upstream design ../../agents/evals/results/hook-runs/README.md defines hook-result accumulation.
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated eval evidence.
downstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py consumes accumulated evidence.
@dependency-end
-->

issue_id: AC-20260517-eval-accumulation-gaps
status: in_progress
source: user
severity: S1
evidence: User feedback on 2026-05-17: eval collection is still not reliably accumulating into AgentCanon.
affected_surfaces: agents/evals/README.md, agents/evals/results/README.md, agents/evals/results/hook-runs/README.md, agents/evals/results/skill-workflow-prompt/README.md, .codex/hooks/hook_event_log.py, .codex/hooks/skill_usage_logger.py, tools/agent_tools/evaluate_skill_workflow_prompts.py, tools/agent_tools/generate_agent_improvement_guide.py
edit_scope: tools/agent_tools/eval_accumulation_check.py, tests/agent_tools/test_eval_accumulation_check.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, tools/ci/run_all_checks.sh, .github/workflows/agent-canon-static-gates.yml
required_action: Add a gate that verifies AgentCanon-owned hook and skill eval result directories are append-only, tracked, and structurally readable.
close_condition: The gate passes on current accumulated evidence and fails on missing result directories, duplicate hook run ids, malformed JSONL, or ignored result paths.

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
