<!--
@dependency-start
contract skill
responsibility Documents Lean-first algorithm design before implementation.
upstream design ../canonical/skills.md skill canon registry
upstream design ./formal-proof-workflow.md checker-backed formal proof workflow
upstream design ./algorithm-proof-exploration.md implementation-derived algorithm proof exploration
upstream design ./computational-optimization.md optimization contract for numerical algorithms
downstream design ../../.agents/skills/lean-algorithm-design/SKILL.md Codex discovery shim
downstream design ./catalog.yaml public skill catalog entry
@dependency-end
-->

# lean-algorithm-design

## Purpose

Use this skill when an algorithm should be designed in Lean before production
implementation. The skill is independent of existing production code paths: it
models candidate algorithms as mathematical transition systems, proves or
refutes the desired contract, and only then hands a checked design contract to
implementation or implementation-derived proof workflows.

## Use When

- The user asks to design an algorithm on the Lean side before coding.
- Multiple algorithmic mechanisms are possible and the proof should choose
  among them before production code exists.
- The task is about convergence, finite stopping, classification, certificate
  soundness, filter/restoration logic, line search, or inner-solver contracts.
- Existing implementation proof attempts have drifted, and a clean design
  model is needed before changing code.

## Boundary

- This skill owns pre-implementation mathematical design and checker-backed
  algorithm selection.
- `$algorithm-proof-exploration` owns proving or repairing an existing
  implementation route after a production entrypoint exists.
- `$formal-proof-workflow` owns terminal proof adoption, refutation, and
  checked proof-status artifacts.
- `$computational-optimization` owns the numerical optimization contract:
  objective/residual, variables, constraints, derivatives, stopping policy,
  invariants, and failure semantics.

## Workflow

1. State the design target before writing Lean:
   - problem family and allowed assumptions
   - algorithm state and transition map
   - stopping or certificate predicate
   - result classification semantics
   - inner-solver contract, if the outer step depends on one
1. Create a fresh Lean design namespace under `lean/<topic>/` that does not
   import generated implementation evidence unless the task explicitly asks to
   compare with existing code.
1. Encode the candidate algorithm as Lean definitions:
   - problem structure
   - state structure
   - transition relation or transition function
   - acceptance / restoration / line-search predicates
   - inner-solver input-output contracts
   - returned certificate predicates
1. Prove local structural theorems first, but only when they feed the design
   target. Examples: epigraph equivalence, filter-progress implication,
   restoration acceptance, inner-solver contract composition, ranking decrease.
1. State the target theorem over the Lean design API, not over production
   helpers. For iterative algorithms, the theorem should consume a transition
   map and a stopping scalar or certificate predicate.
1. Use Mathlib, Aesop, SMT / counterexample tools, and theorem search where
   available. Do not create private proof frameworks when existing Lean
   libraries cover the algebra, order, recurrence, or graph reasoning.
1. If the theorem fails, classify the reason as one of:
   - algorithm mechanism is too weak
   - assumptions are too weak
   - theorem is too strong
   - inner-solver contract is insufficient
   - Lean model is missing a required algorithm component
1. Iterate on the algorithm, not production code, until the design target is
   proved, refuted, or restricted to a checked problem class.
1. Only after Lean design checks pass, write an implementation handoff:
   - Lean definitions that are the source design
   - checked theorem names and `lake build` command
   - production API fields required by the theorem
   - implementation constraints, including forbidden proof-only runtime fields
   - validation and later implementation-derived proof route

## Rules

- Do not use existing production helpers as the design model. The design model
  is mathematical and local; production code is added later.
- Do not add proof-only fields to production `Info`, config, or state.
- Do not accept a theorem that closes only by defining the condition as the
  target itself; run graph or dependency checks for circularity when a problem
  class is claimed.
- Do not report a list of missing lemmas as completion. Either prove/refute the
  design target or return a checked direct design boundary.
- For optimization algorithms, keep feasibility, objective progress, local
  optimality, infeasibility, and unboundedness certificates separate.
- For nested solvers, keep inner-solver contracts parametric in quantities the
  caller owns; substitute caller bounds only at the outer theorem.

## Outputs

- `lean_design_model`: Lean definitions for the candidate algorithm.
- `lean_design_theorems`: checked theorem names and validation command.
- `design_frontier`: refuted or open design obligations with checker evidence.
- `implementation_handoff`: production API and algorithm constraints derived
  from the checked Lean design.
