Dependency Files:

- vendor/agent-canon/AGENTS.md
- vendor/agent-canon/agents/canonical/ARTIFACT_PLACEMENT.md
- vendor/agent-canon/documents/dependency-headers.md
- vendor/agent-canon/tools/agent_tools/bootstrap_agent_run.py
- vendor/agent-canon/tools/agent_tools/task_start.py

# Agent Templates

This directory contains run-bundle and review templates emitted by the agent-canon tooling. The templates are durable artifacts: each one defines a role output, gate, review note, or closeout record that a workflow can place under `reports/agents/<run-id>/`.

## Template Families

- Intake and planning: `intent_brief.md`, `user_request_contract.md`, `schedule.md`, `work_log.md`, `decision_log.md`.
- Design and test planning: `design_brief.md`, `design_review.md`, `document_flow_review.md`, `test_plan.md`.
- Review gates: `change_review.md`, `final_review.md`, `artifact_review.md`, `project_review.md`, `python_review.md`, and the specialist review templates.
- Validation and closeout: `verification.txt`, `closeout_gate.md`, `retrospective.md`.

## Producers And Consumers

`tools/agent_tools/bootstrap_agent_run.py` and `tools/agent_tools/task_start.py` instantiate these templates. Workflow documents and subagent manifests consume them as the canonical artifact names for stage handoff.

When adding or editing a template, update its dependency header to include this README, the workflow or review policy it implements, and the tool that emits or validates it.
