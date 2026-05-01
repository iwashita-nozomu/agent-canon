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
- run_safety_cap: 5
- current_iteration: 2
- active_run_id: 20260501-oop-readability-loop
- stop_reason:

## Objective

Improve OOP readability across all repository code using
`tools/agent_tools/analyze_oop_readability.py` as the fixed mechanical
evaluation. The loop should keep running backlog-driven iterations until the
accepted OOP risk is reduced enough to stop explicitly, without changing runtime
behavior, public API semantics, or numerical algorithms.

## Exit Criteria

- [x] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [x] G2: Code dependency extraction is reviewed with `bash tools/agent_tools/scan_code_dependencies.sh` for the affected surface.
- [ ] G3: OOP/readability analysis is run over all code paths before and after the current iteration with the same path set and threshold.
- [ ] G4: The current iteration reduces accepted OOP findings or score-risk concentration without adding behavior changes.
- [ ] G5: Repo-wide static analysis or CI passes with `make ci`, or the documented fallback `python3 -m pyright` plus `python3 -m ruff check python tests --select D,E,F,I,UP`.
- [ ] G6: Objective-specific completion evidence, baseline report, final report, and next backlog decision are recorded.

## Backlog

- [x] B1: Establish the all-code OOP readability baseline and hotspot ranking.
- [x] B2: Classify hotspot findings into behavior-preserving refactor candidates and intentional/value-object exceptions.
- [x] B3: Apply iteration 1 behavior-preserving refactor pass to AgentCanon helper hotspots.
- [x] B4: Rerun iteration 1 all-code OOP readability evaluation and compare baseline versus final counts.
- [ ] B5: Continue with iteration 2 on the next highest accepted hotspot cluster.
- [ ] B6: Rerun the all-code OOP readability evaluation after iteration 2.
- [ ] B7: Record remaining backlog and explicit continue/stop decision.

## Loop Log

- iteration 1: started all-code OOP readability improvement loop.
- iteration 1 result: all-code OOP findings decreased from 834 to 828. This was
  a completed extension, not loop termination.
- iteration 2: continue the loop on the next accepted hotspot cluster; remaining
  backlog is led by `PrimitiveDerivativeBridgePass.cpp`, `smolyak.hpp`,
  `native_autodiff.hpp`, and `kokkos_backend.hpp`.
