---
name: algorithm-proof-exploration
description: Use when exploring, refactoring, or choosing an algorithm under proof obligations; builds Algorithm Expansion IR, lemma dependency graphs, algorithmic blocker frontiers, and algorithm-change guidance before handing terminal proof work to formal-proof-workflow.
---

<!--
@dependency-start
responsibility Exposes theorem-driven algorithm exploration to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/algorithm-proof-exploration.md canonical skill document
upstream design ../../../agents/skills/formal-proof-workflow.md checker-backed claim workflow.
upstream implementation ../../../tools/agent_tools/algorithm_expansion_ir.py builds implementation IR.
upstream implementation ../../../tools/agent_tools/algorithm_lemma_graph.py builds lemma graphs.
upstream implementation ../../../tools/agent_tools/proof_path_analyzer.py checks proof-status overlays.
upstream implementation ../../../tools/agent_tools/algorithm_flowchart.py renders implementation/proof-state Mermaid diagrams.
upstream implementation ../../../tools/agent_tools/ir_graph_correspondence.py checks IR equation facts against lemma graphs.
upstream implementation ../../../rust/agent-canon/src/algorithm_ir_to_lean.rs lowers IR facts into Lean route artifacts.
upstream implementation ../../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections from IR facts.
upstream design ../../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop capabilities by frontier shape.
@dependency-end
-->

# Algorithm Proof Exploration

1. Read `agents/skills/algorithm-proof-exploration.md`.
1. Use `$formal-proof-workflow` with this skill. This skill owns algorithm
   exploration: implementation degrees of freedom, algorithmic blockers,
   candidate changes, runtime certificates, and problem-class witnesses.
   `$formal-proof-workflow` owns proof-route exploration, formal proof adoption,
   final checker-backed proof, refutation, or unprovability claims.
1. Fix the target theorem first: local convergence, certificate soundness,
   finite-precision floor, solver-chain reachability, infeasibility certificate,
   or another named theorem. Do not explore helpers without a theorem target.
1. Build Algorithm Expansion IR from the public root consumed by the theorem:
   `initialize`, `solve`, `step`, or a certificate-returning function.
   Use saturated AST expansion; do not add caller-chosen recursion-depth knobs.
1. Preserve code shape as executable proof functions before theorem search.
   When the target theorem talks about a concrete implementation path, every
   target-facing data transformation on that path must appear as a Lean
   function or generated trace function, not as an arbitrary axiom: residual
   aggregation, residual recomputation, step-length selection, next-state
   update, KKT reconstruction, and stopping metric construction are all code
   shape.  If the current IR-to-Lean bridge only exposes an opaque evaluator,
   add or improve a checker-facing adapter that mirrors the implementation
   fields and record the IR source facts it consumes.  Leave axioms only for
   explicit backend/runtime semantics or problem-owned analytic functions
   admitted at the top-level theorem.
1. Treat the implemented algorithm itself as an operational assumption:
   `trace follows A_impl / Step_impl` extracted from IR. Convergence,
   certificate soundness, finite termination, and residual reachability are
   lemmas derived from that assumption, not assumptions.
1. Convert the IR into one or more Lemma Dependency Graph profiles. Keep
   generated IR-backed nodes synchronized only by regenerating IR after source
   code changes. If the algorithm changes, reset generated lemma groups and
   rebuild the proof-status overlay from the current IR instead of carrying old
   lemmas forward by hand.
   Also regenerate the checker-facing Lean route artifacts with
   `tools/bin/agent-canon algorithm-ir-to-lean`; do not continue a proof
   route through a hand-written operation abstraction when the implementation path
   can be represented from current IR `expression_ast` and `control_facts`.
   Structure access must be normalized by the Rust post-IR projection pass, not
   by algorithm-specific generated shapes.
1. When the user asks what iterative algorithm is currently implemented or
   which blocks are proved/open, run `$algorithm-flowchart` after IR and
   LemmaGraph generation. The Mermaid chart is visualization evidence; proof
   completion still comes from checker-backed fragments.
   Use `--view runtime` or `--view core --include-code-facts` when the chart
   must show implementation flow without proof-only labels or branches.
1. For reduced block-system / KKT / iterative-solver-chain equations, use
   `python3 tools/agent_tools/kkt_equation_section.py` or the relevant
   equation-section generator with the current Algorithm Expansion IR files. Missing required evidence is
   an IR extraction or code-shape issue, not a reason to hand-maintain proof
   prose. The generated section owns the displayed implementation formulas by
   substituting matched IR `code_facts[*].expression` values; proof notes should
   link to that section instead of carrying parallel hand-written runtime
   equations.
1. Hand-translate theorem-critical IR equations into candidate typed
   mathematical Lean propositions. IR fact extraction tells which equations are
   present; the skill must still explore which proposition states the useful
   mathematical guarantee. Do not freeze on the first bridge shape. Generate
   multiple bridge candidates at the abstraction level required by the target
   theorem, check or refute them when possible, and classify each candidate
   before choosing the next proof route. Do not leave theorem-critical returned
   values unconstrained when the current IR contains equations that determine or
   bound them.
1. Drive candidate selection recursively from the final theorem, not from a
   flat list. State the current target proposition `P`, run the checker/tactic
   search (`aesop?`, `aesop`, `simp?`, `exact?`, or the route selected by
   `$formal-proof-workflow`), record the unsolved subgoals or missing
   hypotheses, translate each missing item into candidate bridge propositions,
   check whether current Lean functions / generated IR facts can prove or
   refute those candidates, then rerun the target proof. Repeat until `P` is
   proved, refuted, shown unprovable under the current top-level assumptions, or
   reduced to a strictly smaller named witness.
1. For theorem-critical intermediate formulas, use
   `python3 tools/agent_tools/ir_graph_correspondence.py` after LemmaGraph
   generation. Check assignment and return equations per iteration unit
   (`source_symbol` plus `equation_tags`, such as `step_update` or
   `reduced_kkt`) before handing them to `$formal-proof-workflow`. If the
   correspondence checker reports a missing graph node or consumption edge,
   fix IR extraction or graph generation instead of hard-coding prose equations.
1. Treat the lemma graph as the editable algorithm exploration surface. Agents
   and humans may add candidate algorithm changes, certificate edges, source
   packets, and formal-proof handoff decisions as overlay data, but must not
   hand-edit generated IR facts into a proof result.
1. Extract an algorithm frontier from the graph, not from prose order. Pick
   target-facing blockers by algorithmic impact and reduce each to one of:
   implementation identity, certificate plumbing, reachability/existence
   mechanism, algorithmic choice, external assumption binding, or problem-class
   witness.
1. Do not treat a failed single-lemma formal-proof route as an algorithm
   failure. Hand proof-route alternatives to `$formal-proof-workflow`; use its checker-backed
   outcome to decide whether an algorithm change is actually needed.
1. Before classifying a current algorithmic choice as the blocker, require
   `$formal-proof-workflow` to propositionize every target-facing algorithm
   block whose returned value can affect the theorem. For iterative solvers,
   this includes the initializer, stopping scalar, step-length or acceptance
   selection, direction construction, nested solver certificate, state update,
   residual/merit recomputation, and final scalar binding. If any such block is
   still only a route call or unconstrained theorem variable, send it back as a
   smaller formal-proof witness. An algorithmic blocker is visible only when
   the remaining gap is a semantic mechanism such as missing contraction,
   missing residual-merit selection, missing problem-class bound, missing
   backend boundary, or checker-backed refutation.
1. When formal-proof returns a missing witness or assumption-insufficiency
   result, classify whether the gap is better solved by changing the algorithm,
   adding a runtime certificate, narrowing the problem class, or leaving an
   external assumption boundary.
1. Do not solve a frontier by injecting assumptions unrelated to the target
   algorithm inputs. For a fixed algorithm, all mathematical assumptions live at
   the theorem top level and are over the target `Problem` and config object.
   Intermediate frontier claims are problem/config-derived lemmas that must be
   proved from those top-level assumptions plus the extracted code path.
   Architecture assumptions such as the implementation trace and backend/runtime
   semantics are allowed only as architecture boundaries, and must be labeled
   separately from Problem/config assumptions.
1. Treat a desired local assumption as a derivation target, not as a premise.
   For each desired intermediate condition, run a try-and-error derivation loop:
   name the condition as a candidate lemma, bind every variable to either
   `Problem`, config, the IR-extracted path state, a code fact, or an allowed
   architecture boundary, then ask `$formal-proof-workflow` to prove it from the
   top-level assumptions plus the code path. If the route fails, change the
   lemma shape before changing the theorem: try quotient/projection forms,
   upper-bound lemmas, selected-scope certificates, finite-prefix certificates,
   same-units conversion, or returned-runtime certificates that are useful to
   the algorithm. Do not promote the desired condition into an independent
   assumption. If no derivation route closes, return the minimal blocker as
   either missing top-level problem/config property, missing external
   architecture evidence, or an algorithmic choice that must change.
1. For initialization, basin-entry, or selected-scope-entry blockers, normalize the
   implementation as a selected initializer
   `z_init = Init(Problem, InitializeConfig)`. Do not promote a hard-coded zero,
   default vector, supplied state, or previous-state reuse into a theorem
   premise unless the algorithm genuinely requires that value and the IR code
   facts show the specialization. If the selected initializer is too weak,
   classify the gap as either a problem-class witness for that initializer or
   an algorithmic choice to add a stronger initializer, Phase I, or
   globalization path.
1. If the gap is a current algorithmic choice, enumerate the smallest
   implementation degrees of freedom that could make the target theorem
   provable and translate each candidate into a proof obligation before editing
   code. After any algorithm change, regenerate IR/graphs and re-enter the same
   algorithm frontier; do not stop at guidance when the target theorem can still
   be tested by `$formal-proof-workflow`.
1. After changing initialization logic, require `$formal-proof-workflow` to
   consume the newly extracted initialization code facts before returning to
   the user. Code-visible selected initial point, epigraph point,
   slack/multiplier floor, initial residual, and child-solver state facts are
   not acceptable user-facing blockers.
1. When the code must change for provability, state the algorithm change in
   proof terms first: expose a runtime certificate, remove an unsound gate,
   strengthen a returned residual certificate, change the blocking algorithmic
   choice, replace hard-coded initial points with a proof-visible selected
   initializer, add Phase I/globalization, narrow to a local theorem, or add a
   problem-class witness.
1. Do not treat frontier classification or algorithm-change guidance as the
   skill completion condition. Completion requires a checker-backed result for
   the target theorem itself: either the target theorem is proved, or it is
   proved that the current assumptions and implementation path are insufficient
   to derive that theorem.
1. Treat `unverified_with_next_witness` as a handoff queue back to
   `$formal-proof-workflow`, not as algorithmic completion. Re-enter that named
   witness until the proof workflow returns `verified`, `refuted`,
   `unprovable_under_assumptions`, or a strictly smaller frontier witness.
1. If an algorithm change is needed, continue until either the current
   assumptions are proved insufficient or the changed algorithm has a
   checker-backed proof of the target theorem. A proposed change alone is only
   `algorithm_change_guidance`.
1. Do not add proof-only fields to production `InitializeConfig` or algorithm
   state. Proof-only backend profiles and theorem variables belong in
   `lean/lib/`, Algorithm Expansion IR, or graph overlays.
1. Store checker-facing IR, lemma graphs, proof overlays, and Lean stubs under
   `lean/<proof-theme>/`. Store reader-facing mathematical proof notes under
   `notes/themes/`.
1. Before reporting progress, run `proof_path_analyzer.py` against the current
   lemma graph, proof status overlay, frontier/handoff artifact, and proof
   note. A valid connected path is structure evidence, not proof completion.
1. Hand terminal proof obligations to `$formal-proof-workflow`: checked theorem
   statements, counterexamples, unprovable-under-assumptions witnesses, existing
   proof search packets, and checker commands.

## Outputs

- `proof_algorithm_ir`: root, target theorem, selected obligations, code facts.
- `proof_lemma_graph`: target chains, generated nodes, overlay candidates.
- `proof_algorithm_flowchart`: generated Mermaid or Markdown diagram showing
  implementation blocks and proof-state overlay.
- `proof_operational_assumptions`: implemented trace premise consumed by the
  final theorem.
- `algorithm_frontier`: current algorithmic blockers, candidate changes, and
  formal-proof handoff targets.
- `proof_frontier`: theorem-facing graph frontier sent back to formal proof
  work when an algorithmic change is not yet justified.
- `algorithm_change_guidance`: code changes needed to make a theorem provable.
- `formal_proof_handoff`: exact claims and artifacts for
  `$formal-proof-workflow`.
