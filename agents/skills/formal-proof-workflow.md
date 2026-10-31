# formal-proof-workflow

<!--
@dependency-start
contract skill
responsibility Documents the natural-language to formal-proof workflow.
upstream design ../canonical/skills.md skill canon registry.
upstream design lean-algorithm-design.md Lean-first algorithm design workflow.
upstream design algorithm-proof-exploration.md proof-guided algorithm exploration workflow.
upstream design literature-survey.md source search and bibliography workflow.
upstream design research-workflow.md external research and implementation loop.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/lean_proof_env.rs creates Lean proof-search, theorem-search, and counterexample environments.
upstream design ../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop/Plausible/LeanSearchClient capabilities by proof-frontier shape.
upstream implementation ../../tools/analysis/proof/jit_canonical_ir.py extracts StableHLO-derived thin operational IR and backend traces.
upstream implementation ../../tools/analysis/code/cpp_source_canonical_ir.py extracts C++ source-canonical IR into thin operational IR.
upstream implementation ../../tools/analysis/proof/operational_ir_to_lean.py renders thin operational IR into Lean evidence definitions.
upstream implementation ../../tools/analysis/proof/cpp_template_to_lean.py fully expands C++ template roots into Lean evidence.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant references.
downstream implementation ../../.codex/personal/skills/formal-proof-workflow/SKILL.md exposes the skill to Codex.
upstream design code-visualization.md visualization selection and native renderer delegation
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this adapter dependency header
@dependency-end
-->

## Purpose

Turn a mathematical claim, proof sketch, or implementation claim into a precise
target that a supported formal checker can establish, refute, or leave unresolved.
Natural-language reasoning, generated scaffolds, and unchecked theorem files are
inputs to this work; they are not proof evidence.

## Use When

- A mathematical or design claim needs checker-backed evidence.
- Existing formal results or libraries may discharge a claim or its lemmas.
- An implementation-derived claim needs a checked link from code behavior to a
  mathematical property.

## Core Method

1. State the requested conclusion and separate its assumptions, definitions,
   and theorem target. Keep the formal statement within the caller's intended
   scope; expose assumptions that affect the result.
2. Reuse available proofs, lemmas, libraries, checker environments, and data
   producers before adding a new mechanism. Use an existing native extension
   point when it covers the task; add new code only for a demonstrated gap.
   Do not duplicate an existing capability with another wrapper, dispatcher,
   runner, or schema.
3. Choose a proof tool and command that the caller's project actually supports.
   The listed Lean, Isabelle, Coq/Rocq, and SMT routes are options, not a claim
   that every tool is installed. [The formal proof tool guide](../../documents/tools/formal_proof.md)
   describes its planner as scaffold-only; read the
   [Lean capability matrix](../../documents/tools/lean_capability_matrix.md)
   only when Lean is selected.
4. If the claim is about an implementation, bind the theorem to the actual
   public inputs, selected implementation path, and observable output. Extract
   only the code path and equations needed to establish that link, using the
   existing route for the language and source form. Abstract mathematical
   claims do not require code extraction, IR, or a theorem graph. Do not treat
   an intermediate runtime value as an independent assumption when it must be
   derived from those public inputs and the selected path.
5. Check the target theorem, not just an intermediate lemma or generated file.
   Do not count a compile, generated IR, scaffold, search result, or graph edge
   as proof. A completed proof has no `sorry`, `admit`/`Admitted`, circular
   assumption, or equivalent hole; disclose the axioms and trust basis that
   remain in the checked result.

## Evidence Status

| Status | Meaning |
| --- | --- |
| `verified` | The declared target checks under the stated assumptions and trusted base. |
| `refuted` | A checked counterexample violates the target in its declared scope. |
| `unprovable_under_assumptions` | A checked model satisfies the assumptions while making the target false, showing it is not entailed by those assumptions. |
| `unproven` | The target remains open; failed search or a difficult proof is not a refutation. |
| `incomplete` | Required formalization, checker execution, or implementation-to-theorem link has not been completed. |

A checker, extraction, build, or environment failure is an infrastructure result,
not mathematical refutation. Route it to the owner of that failing mechanism. For
`refuted` or `unprovable_under_assumptions`, retain the counterexample, model, or
witness and show that it satisfies the declared assumptions. Distinguish those
outcomes from an unresolved proof attempt.

## Boundaries And Related Skills

- If proving the claim requires choosing or changing an algorithm, use
  [`algorithm-proof-exploration`](algorithm-proof-exploration.md) to examine the
  algorithmic mechanism, then return the target and evidence here for checker-backed
  proof status.
- If an algorithm must be designed and proved before implementation, use
  [`lean-algorithm-design`](lean-algorithm-design.md) for that design contract.
- For an implementation-derived Python algorithm, the existing exploration route
  is JIT-canonical IR and its Lean lowering. The C++ importers are separate
  formal-evidence mechanisms; their existence does not imply that the same
  algorithm-exploration route supports C++.
- If an abstract proof needs external literature or source discovery, use
  [`literature-survey`](literature-survey.md) for that work.
- A proof or algorithm visualization may use [`code-visualization`](code-visualization.md)
  when useful. The visualization communicates selected native evidence; it does
  not establish proof status.

Proof work must not change production behavior, public API, or runtime inputs only
to make a theorem pass. If a checked mismatch indicates the algorithm itself must
change, return that evidence to its mathematical owner. Report the target,
assumptions, checker and result, relevant proof artifact, and unresolved limits;
include the implementation path only when the claim depends on it.
