# computational-optimization

<!--
@dependency-start
contract skill
responsibility Documents computational optimization workflow for numerical algorithms.
upstream design ../canonical/skills.md skill canon registry
upstream design research-workflow.md research-backed change boundary
upstream design experiment-lifecycle.md experiment execution and rerun boundary
upstream design test-design.md adversarial test design boundary
upstream design ../../documents/design/semantic-responsibility-contract.md semantic obligation and verification-owner contract
downstream implementation ../../.codex/personal/skills/computational-optimization/SKILL.md Codex discovery shim
@dependency-end
-->

## Purpose

Clarify the mathematical contract and evidence needed for numerical optimization,
solvers, derivatives, constraints, convergence, and numerical performance work.
Fit the detail to the requested behavior; there is no mandatory field packet for
every numerical question.

## Use When

- A change or diagnosis concerns an optimizer, solver, preconditioner, objective,
  residual, constraint, derivative, stopping rule, tolerance, or numerical status.
- A convergence regression, non-finite result, or numerical performance claim is
  in scope.

## Core Method

Follow [Before optional changes](#before-optional-changes) when implementing or
tuning a numerical method.

1. State the requested numerical property in terms of the public contract. Record
   only the relevant parts of the problem: for example objective or residual,
   variables and parameters, constraints, derivatives, iteration state, stopping
   policy, and failure semantics. Keep correctness questions separate from speed
   claims.
2. Reuse the caller's existing solver, numerical library, oracle, and data
   producer before adding a mechanism. If implementation work reveals a concrete
   gap, use an existing extension point where possible instead of duplicating a
   wrapper, runner, dispatcher, or schema.
3. Trace the property through the current implementation. For an iterative
   method, identify the relevant update, accepted step, stopping quantity, and
   terminal status. Diagnose a failure from the first contract-violating state
   or iteration and its preceding finite values; a final NaN, residual, or test
   assertion alone does not establish the cause.
4. Validate the property with evidence appropriate to the caller's contract and
   prescribed execution path. Do not relax tolerances, alter expected values,
   skip cases, or treat `not_converged`, `max_iter`, non-finite state, or a
   constraint violation as success. Retain and report the observed failure
   status. Require GPU evidence only when the request, contract, or runtime
   profile requires GPU behavior; numerical subject matter alone does not.
5. For performance claims, compare the same mathematical problem, initial
   state, stopping policy, workload, and relevant dtype/backend context. Separate
   numerical trajectory and algorithmic work from execution cost such as compile,
   per-iteration, transfer, or synchronization time. Total time alone cannot
   attribute a regression. When diagnosing iterative-solver performance, use the
   existing [`numeric-performance`](../../tools/runtime/dispatch/agent-canon/src/numeric_performance.rs)
   command (`tools/bin/agent-canon numeric-performance --input <post-run-observations.json> --format json`) and follow its current input and output contract; do not recreate its
   schema or infer a systems-level cause from prose alone. This comparison is not
   required for ordinary numerical correctness work.

The convergence of an iterative method is a property of its implemented update
and stopping rule under stated assumptions. Do not add proof-only state, runtime
proof checks, or diagnostic gates to make a convergence claim pass. Preserve the
public numerical contract unless the task authorizes a contract change.

## Before optional changes

Begin with the agreed existing implementation or the smallest complete version
of the requested method, using the project's established defaults and runner.
Include mechanisms required by the user's method, approved contract, or a
supported mathematical derivation of that requirement. Do not remove a required
line search, preconditioner, or other method component to invent a simpler baseline.

Before adding an optional numerical or performance mechanism, obtain or reuse
actual baseline numerical results or failures under the selected authorized
route. Compilation, a smoke exit, an unrun prediction, or a method's popularity
is not that evidence. Build, launcher, or environment errors do not establish a
numerical deficiency. Do not add speculative epsilon, clipping, damping, scaling,
cache, or parallel variants just in case. Do not silently absorb your own
unapproved tweaks into the baseline; distinguish them from the agreed method.

Tie an additional candidate to an observed deficiency, its supported cause or
explicit hypothesis, and the quantity that can test it. Compare changes in an
interpretable unit while preserving the inputs, oracle, stopping and failure
semantics; retain the baseline failure rather than masking it as success.
Source- or specification-proven algorithm errors can be repaired directly:
this rule does not require running a known-invalid implementation, benchmarking
ordinary correctness repairs, or executing a theory-only request.

If execution is held or unavailable, state what remains unobserved and defer
optional tweaks; continue independent authorized baseline implementation or
explanation. This rule grants no new execution authority and does not require
rerunning valid existing evidence. Changes to scope, method, or acceptance follow
[Decision Order](agent-orchestration.md#decision-order).

## Related Skills

- Use [`algorithm-proof-exploration`](algorithm-proof-exploration.md) when proof
  obligations should guide an algorithm choice or change, and
  [`formal-proof-workflow`](formal-proof-workflow.md) when a formal claim needs
  checker-backed status.
- Use [`research-workflow`](research-workflow.md) for external method comparisons;
  [`experiment-lifecycle`](experiment-lifecycle.md) and
  [`result-artifact-writeout`](result-artifact-writeout.md) for a concrete run
  protocol and its results.
- Use [`test-design`](test-design.md) only when a concrete test-owned runtime risk
  remains after the mechanism and existing validation are understood. Use the
  [semantic responsibility contract](../../documents/design/semantic-responsibility-contract.md)
  when a change crosses owners and its obligations need allocation.
- For JAX loop implementation details, consult
  [the JAX rules](../../documents/conventions/python/15_jax_rules.md) only when
  that implementation route is selected.
- Route numerical behavior review to `scientific_computing_reviewer`, performance
  claims to `benchmark_reviewer`, and language-specific implementation diffs to
  `$python-review` or `$cpp-review` as applicable. Non-numerical C++ performance
  stays on the C++ review route.

Report the contract details relevant to the task, observed state and likely cause
separately from unconfirmed hypotheses, and the validation evidence with its
actual backend and limits. Include performance decomposition only when the claim
is about performance.
