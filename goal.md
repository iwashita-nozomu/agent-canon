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
- current_iteration: 5
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
- [x] G3: OOP/readability analysis is run over all code paths before and after the current iteration with the same path set and threshold.
- [x] G4: The current iteration reduces accepted OOP findings or score-risk concentration without adding behavior changes.
- [x] G5: Repo-wide static analysis or CI passes with `make ci`, or the documented fallback `python3 -m pyright` plus `python3 -m ruff check python tests --select D,E,F,I,UP`.
- [x] G6: Objective-specific completion evidence, baseline report, final report, and next backlog decision are recorded.

## Backlog

- [x] B1: Establish the all-code OOP readability baseline and hotspot ranking.
- [x] B2: Classify hotspot findings into behavior-preserving refactor candidates and intentional/value-object exceptions.
- [x] B3: Apply iteration 1 behavior-preserving refactor pass to AgentCanon helper hotspots.
- [x] B4: Rerun iteration 1 all-code OOP readability evaluation and compare baseline versus final counts.
- [x] B5: Continue with iteration 2 on the next highest accepted hotspot cluster.
- [x] B6: Rerun the all-code OOP readability evaluation after iteration 2.
- [x] B7: Record remaining backlog and explicit continue/stop decision.
- [x] B8: Continue with iteration 3 on the next highest accepted hotspot cluster.
- [x] B9: Rerun the all-code OOP readability evaluation after iteration 3.
- [x] B10: Record remaining backlog and explicit continue/stop decision.
- [x] B11: Continue with iteration 4 using subagent-supported candidate selection.
- [x] B12: Rerun the all-code OOP readability evaluation after iteration 4.
- [x] B13: Record remaining backlog and explicit continue/stop decision.
- [x] B14: Continue with iteration 5 using subagent-supported candidate selection.
- [x] B15: Rerun the all-code OOP readability evaluation after iteration 5.
- [x] B16: Record remaining backlog and explicit continue/stop decision.

## Loop Log

- iteration 1: started all-code OOP readability improvement loop.
- iteration 1 result: all-code OOP findings decreased from 834 to 828. This was
  a completed extension, not loop termination.
- iteration 2: continue the loop on the next accepted hotspot cluster; remaining
  backlog is led by `PrimitiveDerivativeBridgePass.cpp`, `smolyak.hpp`,
  `native_autodiff.hpp`, and `kokkos_backend.hpp`.
- iteration 2 result: grouped callable and bulk layout count fields in
  `PrimitiveDerivativeBridgePass.cpp` without changing descriptor ABI or IR
  generation order. All-code OOP findings decreased from 831 to 829, and the
  target file decreased from 52 to 50. Decision state is `backlog_continue`;
  the loop remains open for validation, commit / push, and the next backlog
  item.
- iteration 2 validation: `cmake --build build --target
  native_autodiff_bridge_pass_test native_autodiff_pipeline_smoke
  native_autodiff_clang_normalization_smoke`, matching `ctest` compiler-pass
  subset, repo dependency review, and `make ci` passed. Next backlog remains
  open; likely targets are `agent_team.py`, `smolyak.hpp`, `native_autodiff.hpp`,
  or `kokkos_backend.hpp`. `goal_status` stays `active`.
- iteration 3: continue the loop on the next accepted hotspot cluster, starting
  from all-code OOP findings 829.
- iteration 3 result: annotated `make_run_id` in `agent_team.py` with its
  concrete `datetime` input type. All-code OOP findings decreased from 829 to
  828, and the target file decreased from 34 to 33. Decision state is
  `backlog_continue`; validation and commit / push remain open before advancing
  again.
- iteration 3 validation: targeted agent-team pytest subset, repo dependency
  review, and `make ci` passed. Next backlog remains open; likely targets are
  `smolyak.hpp`, `native_autodiff.hpp`, `kokkos_backend.hpp`, or deeper
  `agent_team.py` structure. `goal_status` stays `active`.
- iteration 4: parent manages the loop state and gates; subagents handle
  read-only candidate selection, validation design, and one bounded writer
  slice. Starting baseline is all-code OOP findings 828.
- iteration 4 update: Python report assembly refactor reduced
  `evaluate_agent_run.py` findings from 10 to 1. C++ registry pass refactor
  reduced `PrimitiveRegistryPass.cpp` findings from 20 to 18 and lowered that
  file from severe-risk to low-risk. Source-tree OOP findings are 828 to 818.
  Targeted Python tests, targeted C++ build/tests, and repo dependency review
  passed. Repo-wide `make ci` is pending until upstream AgentCanon sync can run
  from a clean worktree.
- iteration 4 validation: upstream AgentCanon was synchronized and pushed to
  `/mnt/git/agent-canon.git`. `make ci` passed with 171 pytest tests plus 6
  subtests, pyright, pydocstyle, and ruff. Remaining backlog continues with
  `PrimitiveDerivativeBridgePass.cpp`, `smolyak.hpp`, `native_autodiff.hpp`,
  `kokkos_backend.hpp`, and deeper C++/Python readability hotspots.
- iteration 5: loop continues because the objective still has high-risk
  hotspots. Parent keeps loop state and validation gates; subagents select the
  next bounded behavior-preserving target before a single write slice starts.
- iteration 5 update: C++ layout validator refactor in
  `PrimitiveDerivativeBridgePass.cpp` removed the targeted validator
  function-length / cognitive-complexity findings. The target file moved from
  high-risk to moderate-risk; source-tree warn findings dropped from 317 to
  311 while total info findings rose from 818 to 820. C++ reviewer approved
  this as risk-concentration reduction. Targeted C++ build/tests and repo
  dependency review passed. Repo-wide `make ci` is pending until upstream
  AgentCanon sync can run from a clean worktree.
- iteration 5 validation: upstream AgentCanon was synchronized and pushed to
  `/mnt/git/agent-canon.git`. `make ci` passed with 171 pytest tests plus 6
  subtests, pyright, pydocstyle, and ruff. The loop remains active because
  `PrimitiveDerivativeBridgePass.cpp`, `agent_team.py`, `smolyak.hpp`,
  `native_autodiff.hpp`, and `kokkos_backend.hpp` still dominate the hotspot
  ranking.
