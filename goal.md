# Goal
<!--
@dependency-start
responsibility Defines the top-level goal loop contract for this repository.
upstream design README.md repository entrypoint
upstream design agents/workflows/adaptive-improvement-workflow.md loop workflow
downstream implementation tools/agent_tools/goal_loop.py consumes this contract
@dependency-end
-->

## Loop Contract

- goal_status: active
- max_iterations: 5
- current_iteration: 2
- active_run_id:
- stop_reason:

## Objective

Improve all skill and workflow prompt surfaces so every current and future skill/workflow
is covered by frozen eval definitions, prompt drift is detected mechanically, and
skill-driven agent behavior is monitored through run-bundle behavior evals until no
prompt or behavior deviation remains.

## Exit Criteria

- [ ] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [ ] G2: Code dependency extraction is reviewed with `bash tools/agent_tools/scan_code_dependencies.sh` for the affected surface.
- [ ] G3: OOP/readability analysis is run with `python3 tools/agent_tools/analyze_oop_readability.py` and findings are fixed or documented.
- [ ] G4: Repo-wide static analysis or CI passes with `make ci`, or the documented fallback `python3 -m pyright` plus `python3 -m ruff check python tests --select D,E,F,I,UP`.
- [ ] G5: Objective-specific prompt and behavior eval completion evidence is recorded.

## Backlog

- [x] B1: Add a machine-readable eval manifest for all discoverable skill shims, human skill docs, and workflow docs.
- [x] B2: Add a deterministic eval runner and tests for skill/workflow prompt drift.
- [x] B3: Update the adaptive-improvement-loop skill and workflow prompts to require eval-driven repair/rerun.
- [x] B4: Run the eval, fix all deviations, then rerun until the eval passes.
- [ ] B5: Add behavior-monitoring eval coverage so skill/workflow prompts require run-bundle agent behavior evidence, not only static prompt text.
- [ ] B6: Extend run-bundle agent evaluation to check behavior signals, subagent lifecycle evidence, diff-check evidence, prompt eval evidence, and feedback-resolution evidence mechanically.
- [ ] B7: Update eval documentation and workflows so behavior evals are managed beside prompt evals.
- [ ] B8: Rerun prompt eval, behavior eval tests, dependency review, readability/OOP analysis, and CI until all gates pass.

## Loop Log

- iteration 1: started eval-driven all-skill/all-workflow prompt hardening.
- iteration 2: started behavior-monitoring eval hardening for skill/workflow execution.
