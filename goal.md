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

- goal_status: achieved
- max_iterations: 5
- current_iteration: 1
- active_run_id:
- stop_reason:

## Objective

Improve all skill and workflow prompt surfaces so every current and future skill/workflow
is covered by frozen eval definitions, prompt drift is detected mechanically, and
prompt repair/rerun continues until no eval deviation remains.

## Exit Criteria

- [x] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [x] G2: Code dependency extraction is reviewed with `bash tools/agent_tools/scan_code_dependencies.sh` for the affected surface.
- [x] G3: OOP/readability analysis is run with `python3 tools/agent_tools/analyze_oop_readability.py` and findings are fixed or documented.
- [x] G4: Repo-wide static analysis or CI passes with `make ci`, or the documented fallback `python3 -m pyright` plus `python3 -m ruff check python tests --select D,E,F,I,UP`.
- [x] G5: Objective-specific completion evidence is recorded.

## Backlog

- [x] B1: Add a machine-readable eval manifest for all discoverable skill shims, human skill docs, and workflow docs.
- [x] B2: Add a deterministic eval runner and tests for skill/workflow prompt drift.
- [x] B3: Update the adaptive-improvement-loop skill and workflow prompts to require eval-driven repair/rerun.
- [x] B4: Run the eval, fix all deviations, then rerun until the eval passes.

## Loop Log

- iteration 1: started eval-driven all-skill/all-workflow prompt hardening.
