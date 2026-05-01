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
- current_iteration: 0
- active_run_id:
- stop_reason:

## Objective

Define the repository-level goal before starting a goal loop.

## Exit Criteria

- [ ] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [ ] G2: Code dependency extraction is reviewed with `bash tools/agent_tools/scan_code_dependencies.sh` for the affected surface.
- [ ] G3: OOP/readability analysis is run with `python3 tools/agent_tools/analyze_oop_readability.py` and findings are fixed or documented.
- [ ] G4: Repo-wide static analysis or CI passes with `make ci`, or the documented fallback `python3 -m pyright` plus `python3 -m ruff check python tests --select D,E,F,I,UP`.
- [ ] G5: Objective-specific completion evidence is recorded.

## Backlog

- [ ] B1: Define the next smallest iteration that can move one unchecked exit criterion.

## Loop Log
