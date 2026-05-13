# Automated Improvement Guide

<!--
@dependency-start
responsibility Records the workflow defect where memory, eval, hook, and issue evidence was not summarized on PR or branch push.
upstream design ../README.md defines durable issue storage
upstream design ../../agents/evals/README.md defines eval and behavior evidence
upstream design ../../agents/evals/results/hook-runs/README.md defines hook result evidence
downstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py generates the guide
downstream implementation ../../.github/workflows/agent-improvement-guide.yml runs the guide on PR and push
@dependency-end
-->

issue_id: AC-20260513-automated-improvement-guide
status: in_progress
source: user
severity: S1
evidence: .github/workflows/agent-improvement-guide.yml
affected_surfaces: .github/workflows/agent-improvement-guide.yml, tools/agent_tools/generate_agent_improvement_guide.py, agents/evals/results/README.md, agents/workflows/agent-canon-pr-workflow.md, tools/README.md, tools/catalog.yaml
edit_scope: .github/workflows/agent-improvement-guide.yml, tools/agent_tools/generate_agent_improvement_guide.py, tests/agent_tools/test_generate_agent_improvement_guide.py, agents/evals/results/README.md, tools/README.md, tools/catalog.yaml, tools/ci/check_github_workflows.py, tests/tools/test_check_github_workflows.py
required_action: Generate a deterministic memory/eval/hook/issues improvement guide on PR and branch push without mutating repository state.
close_condition: GitHub Actions runs the guide on pull_request, push, and manual dispatch, uploads the report artifact, and checker/tests enforce the workflow contract.

## Finding

Memory notes, accumulated prompt evals, hook logs, and durable issues were all
available or planned, but no PR/push-time surface forced them into one
actionable improvement guide.
That made skill / workflow / tool improvement dependent on a local agent
remembering to inspect every evidence family manually.

## Required Fix

- Add a deterministic guide generator that reads AgentCanon evidence surfaces.
- Run it in GitHub Actions for `pull_request`, `push`, and `workflow_dispatch`.
- Upload the report and write it to the GitHub step summary.
- Keep mutation authority with the local Agent / Copilot PR workflow rather than
  letting the Action rewrite skill, workflow, or tool files directly.
