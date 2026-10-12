# algorithm-proof-exploration

<!--
@dependency-start
contract skill
responsibility Documents theorem-driven algorithm exploration before final formal proof adoption.
upstream design lean-algorithm-design.md Lean-first algorithm design workflow.
upstream design formal-proof-workflow.md checker-backed formal proof workflow.
upstream design computational-optimization.md numerical optimization contract workflow.
upstream implementation ../../tools/analysis/proof/jit_canonical_ir.py builds JIT-canonical IR.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
upstream design ../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop capabilities by frontier shape.
downstream implementation ../../.codex/personal/skills/algorithm-proof-exploration/SKILL.md exposes the skill to Codex.
@dependency-end
-->

## Purpose

Use proof obligations to assess algorithm choices or a proposed algorithm change.
The work identifies which mechanism or assumptions could establish the requested
property, then hands checker-backed proof status to
[`formal-proof-workflow`](formal-proof-workflow.md). An algorithm candidate,
extracted representation, or proof-search result is not itself a checked result.

## Use When

- A convergence, stopping, finite-precision, solver-handoff, or certificate claim
  depends on how an algorithm works.
- A proof result could guide a concrete algorithm choice or change.

For an abstract theorem with no algorithm decision, use the formal proof workflow
directly. Use [`lean-algorithm-design`](lean-algorithm-design.md) when an algorithm
must be designed and checked before it is implemented.

## Core Method

1. Bind the requested property to the caller's actual problem and scope. For an
   implementation claim, identify its public entrypoint, inputs, selected code
   path, and observable output. For an abstract design claim, stay at the
   mathematical level.
2. Record only the contract details needed by that property. For an iterative
   implementation this commonly includes the implemented state transition,
   stopping quantity, failure outcomes, and assumptions on problem/configuration;
   do not assume convergence as a premise when it is the target conclusion.
3. Reuse current implementation evidence, libraries, solver primitives, and
   proof tools before creating another representation or helper. When proof of
   an implementation path is needed, use the existing extractor/lowering route
   for that source form. The current JIT-canonical exploration path targets
   compatible Python implementations; C++ source importers do not establish
   equivalent algorithm-exploration support. Do not recreate an existing tool's
   capability as a wrapper, dispatcher, runner, or schema.
4. Compare candidate mechanisms against the theorem obligation. Keep a proposed
   algorithm change distinct from a checked theorem or refutation. A checked
   mathematical counterexample or theorem mismatch can justify returning to the
   algorithm owner; a failed extractor, generated artifact, checker, or runtime
   environment cannot.
5. After an authorized algorithm change, derive evidence from the current
   implementation and recheck the same requested property. Do not carry forward
   stale extracted facts or treat a changed runtime contract, proof-only field,
   or diagnostic gate as proof of the algorithm.
6. Hand the exact target, assumptions, checked evidence, and remaining proof
   question to `formal-proof-workflow` for terminal proof status. Keep an open
   proof question open; do not promote a promising candidate into a result.

## Evidence And Scope

An implementation-derived theorem must connect the actual public inputs through
the selected implementation path to the observable target. The implementation's
operational behavior may be an assumption for the proof, but convergence,
termination, and certificate soundness remain conclusions to establish.

Use IR, backend traces, theorem graphs, or flowcharts only when they answer a
concrete question about the selected implementation. For compatible JIT Python
paths, the existing [JIT-canonical extractor](../../tools/analysis/proof/jit_canonical_ir.py)
and [Lean lowering](../../tools/runtime/dispatch/agent-canon/src/jit_ir_to_lean.rs)
provide that route. An abstract proof, simple algorithm choice, or direct
mathematical counterexample does not require those artifacts. A visualization
shows evidence structure but does not prove the claim.

Keep mathematical mismatch separate from proof-tool failure. Only checker-backed
evidence that the current algorithm fails the target under its stated assumptions
supports changing the algorithm. Route extraction, lowering, checker, and
environment failures to the owner of that mechanism. Do not change a backend,
device, compiler, dtype, public API, production return value, or runtime check to
make a proof pass unless the caller's contract explicitly requires that change.

## Related Skills

- Use [`formal-proof-workflow`](formal-proof-workflow.md) to formalize the target
  and adopt a proof, refutation, or unresolved status.
- Use [`computational-optimization`](computational-optimization.md) when the
  algorithm claim concerns numerical optimization or solver correctness.
- Use [`lean-algorithm-design`](lean-algorithm-design.md) for checked algorithm
  design before production implementation.
- If a selected proof route uses Lean, consult the
  [Lean capability matrix](../../documents/tools/lean_capability_matrix.md).

Return the selected property, relevant context and implementation path when
applicable, the candidate mechanism considered, evidence actually checked, and
the unresolved question or next owner. Choose the smallest representation that
answers the task; no fixed artifact bundle or frontier ledger is required.
