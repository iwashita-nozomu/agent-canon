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
- Implementing a numerical formula or removing unsupported stabilization is in scope.

## Mathematical fidelity

Implement the agreed equations, relevant assumptions, valid inputs, derivatives
and update/stopping rules. Carry only premises needed for this change; refer to
the existing mathematical owner for the rest. Trace each correction to that
formulation before coding. A numerical symptom, a passing test, a library default
or an existing implementation does not supply approval for a different method.

Epsilon denominators, clipping/floors, diagonal jitter, ridge terms, damping,
fallback inverses and non-finite replacement can change the problem or its
failure meaning. Add them only when required by the agreed method; otherwise
present the proposed mathematical change and obtain agreement first. Fix source-
or specification-proven errors directly within the agreed contract.

Equivalent evaluation is an implementation choice when it preserves the function,
domain, derivatives and required update/failure behavior. Explain that equivalence
and use the selected numerical oracle; do not introduce an unrequested parameter
or alter the test tolerance to make the result pass. Preserve required input and
memory-safety boundaries.

## Core Method

Specialize the [common implementation sequence](../canonical/CODEX_IMPLEMENTATION.md#5-implementation)
below, under [mathematical fidelity](#mathematical-fidelity). Optional mechanisms
also use [Before optional changes](#before-optional-changes); performance claims
use [their comparison](#performance-claims). Read those branches when selected.

1. **Establish the mathematics and cause.** Read the agreed formulation, relevant
   assumptions/valid inputs, required property and failure meaning. Trace the
   target and consumed inputs to the first mismatch. For iterations, include the
   update, accepted step, stopping quantity and terminal status; a final NaN or
   failed assertion alone does not identify the cause. Keep observations and
   established causes distinct from unconfirmed hypotheses.
2. **Decide the complete repair and verification before editing.** Reuse the
   existing numerical provider, data producer and independent oracle. Select the
   owning mechanism, necessary caller changes and code/support to retire. Settle
   a method/domain/acceptance change through [Decision Order](agent-orchestration.md#decision-order)
   before dependent edits; a repair derived from the agreed mathematics proceeds.
3. **Implement and remove by responsibility unit.** Complete the API and caller
   changes, delete superseded corrections and exclusive helpers/flags/fallbacks,
   and move tests of retained guarantees to the retained API. Keep required method
   components, valid inputs and safety boundaries. Complete the planned units
   before their final validation; edits and commits are not separate test gates.
4. **Review the final state, then validate.** Compare the resulting computation
   and references with the formulation; repair remaining old paths or missing
   callers first. Format and run the selected product-API checks with independent
   closed-form, reference or invariant evidence, including valid inputs affected
   by a removed correction. Preserve the oracle and tolerances. Report actual
   status/backend/limits: `not_converged`, `max_iter`, non-finite state and constraint
   violations remain failures. GPU evidence follows the requested contract/runtime
   profile, not numerical subject matter alone.

The convergence of an iterative method is a property of its implemented update
and stopping rule under stated assumptions. Do not add proof-only state, runtime
proof checks, or diagnostic gates to make a convergence claim pass. Preserve the
public numerical contract unless the task authorizes a contract change.

## Before optional changes

Use this branch at the repair-decision step only when adding an optional numerical
or performance mechanism. Reuse actual baseline results/failures from the agreed
method, established defaults and authorized runner. Keep its required line search,
preconditioner and other components. Compilation, smoke exits, predictions and
environment failures do not establish a numerical deficiency.

Tie the candidate to the observed deficiency, cause or explicit hypothesis, and
the quantity that can test it. Preserve inputs, oracle, stopping and failure
meaning; obtain agreement for changes to the agreed mathematics. Speculative
epsilon, clipping, damping, scaling, cache and parallel variants stay out of the
baseline. If execution is held/unavailable, report the gap and defer that optional
change while continuing independent authorized work. Reuse valid existing runs.

Source/specification-proven repairs and removal of a known-invalid correction can
proceed directly. They need no run of the known-invalid code, performance benchmark
or execution of a theory-only request.

## Remove unsupported stabilization

Use the [Core Method](#core-method) once, selecting numerical corrections as the
retirement unit. At the decision step, compare their effect on values, derivatives,
updates and status with the agreed formulation. Retain required regularization,
line search, preconditioning, equivalent evaluation and safety checks. Establish
an unsupported correction's mismatch from source or selected evidence; missing
history alone does not prove it unnecessary.

Restore the agreed computation or required failure and retire exclusive support
with its consumers. Update stale expectations to that mathematics while retaining
the independent oracle. Use valid inputs affected by the old floor/clip in final
verification. Follow the same retirement review and validation steps rather than
starting another cleanup round.

## Performance claims

Only for performance work, compare the same mathematical problem, initial state,
stopping policy, workload and dtype/backend. Separate numerical trajectory and
algorithmic work from compile, iteration, transfer and synchronization costs;
total time alone does not identify a cause. Iterative-solver performance diagnosis
uses the existing [`numeric-performance`](../../tools/runtime/dispatch/agent-canon/src/numeric_performance.rs)
command (`tools/bin/agent-canon numeric-performance --input <post-run-observations.json> --format json`)
and its native schema. Ordinary numerical correctness and cleanup need no
performance comparison.

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
