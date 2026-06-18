---
name: algorithm-proof-exploration
description: Use when exploring, refactoring, or choosing an algorithm under proof obligations; builds JIT-canonical IR, lemma dependency graphs, algorithmic blocker frontiers, and algorithm-change guidance before handing terminal proof work to formal-proof-workflow.
---

<!--
@dependency-start
responsibility Exposes theorem-driven algorithm exploration to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/algorithm-proof-exploration.md canonical skill document
upstream design ../../../agents/skills/formal-proof-workflow.md checker-backed claim workflow.
upstream implementation ../../../tools/agent_tools/jit_canonical_ir.py builds JIT-canonical implementation IR and backend traces.
upstream implementation ../../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
upstream implementation ../../../tools/agent_tools/theorem_graph_circularity_check.py checks theorem graph circularity before classifying problem-class conditions.
upstream design ../../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop capabilities by frontier shape.
@dependency-end
-->

# Algorithm Proof Exploration

1. Read `agents/skills/algorithm-proof-exploration.md`.
1. Use `$formal-proof-workflow` with this skill. This skill owns algorithm
   exploration: implementation degrees of freedom, algorithmic blockers,
   candidate changes, numerical convergence witnesses, and problem-class
   witnesses.
   `$formal-proof-workflow` owns proof-route exploration, formal proof adoption,
   final checker-backed proof, refutation, or unprovability claims.
1. Every `formal_proof_handoff` produced by this skill must include the
   `Target Binding Packet` required by `agents/COMMUNICATION_PROTOCOL.md`:
   target theorem, public root / entrypoint and signature, theorem-visible return
   projection, identifier naming plan, generated evidence artifacts, accepted
   top-level assumptions, forbidden assumptions, completion condition,
   validation commands, and unchecked-output policy. If the current algorithm
   frontier cannot fill those fields, the next action is to regenerate / repair
   the IR, theorem graph, or source packet; do not pass a vague blocker summary
   to a proof subagent.
1. Fix the whole target theorem first, rooted at the JIT-canonical public
   entrypoint: normally `main(problem, InitializeConfig, ...) -> Answer / State
   / Info` or the equivalent run function. Local convergence, certificate
   soundness, finite-precision floor, solver-chain reachability, infeasibility
   certificate, and problem-class narrowing are profiles of that whole theorem,
   not starting points. Do not explore helpers without first stating the
   top-level main theorem they decompose.
1. State that top-level theorem over the public root's static argument schema
   and return schema. The theorem surface uses `let out := main problem config`
   and high-level projections of `out.answer`, `out.state`, and `out.info`.
   Do not derive the target theorem from low-level operation ids, bindings,
   regions, frames, trace rows, or generated evaluator internals. Those low-level
   objects are proof evidence used after the public-return projection is fixed.
1. Build JIT-canonical IR from the public root consumed by the theorem:
   a JIT-lowerable `run(problem, config) -> answer`, `solve`, `step`, or
   certificate-returning function. Use StableHLO lowering and backend phase
   trace generation; do not use caller-chosen recursion-depth knobs or
   hand-maintained implementation formulas.
   Do not choose, freeze, or hardcode a backend to make the algorithm theorem
   easier. Backend choice remains a top-level runtime/profile/config input or a
   generated backend witness unless the user request, approved design, public
   API, or config explicitly scopes the algorithm to one backend. Missing
   backend coverage is `backend_evidence_blocker`, not an algorithm proof route.
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
1. Treat bridge, connection, profile binding, and witness instantiation gaps as
   recursive frontier. A missing edge from code fact to theorem variable, solver
   return to caller units, backend profile to finite-precision premise, or
   bridge lemma to caller theorem is not user-facing progress. Continue until
   it is verified, refuted, proved unprovable under current top-level
   assumptions, or reduced to a checked production code / target input /
   backend-runtime boundary.
1. Generate checker-facing Lean evidence modules with
   `tools/bin/agent-canon jit-ir-to-lean`. If the algorithm changes, delete
   stale generated proof-route artifacts and regenerate from the current JIT
   root. Treat the generated evidence layer and the theorem dependency
   graph as separate objects. The generated layer owns root identity,
   StableHLO hash, operational op kinds, dtype coverage, and backend trace
   coverage. The proof graph owns propositions and theorem dependencies. A
   route of the form "theorem X by A, B, f" is valid only when `f` embeds into
   the current generated evidence module, generated code graph, or trace
   produced by the active lowering route, not as a free helper name.
   The generated or projection layer must expose public-root argument schema,
   return schema, return leaf indexes, and high-level projection functions for
   theorem-visible return fields. If these are missing, fix extraction or the
   `main` return shape before exploring low-level theorem candidates.
1. When the user asks what iterative algorithm is currently implemented or
   which blocks are proved/open, run `$algorithm-flowchart` after IR and
   theorem graph generation. The Mermaid chart is visualization evidence; proof
   completion still comes from checker-backed fragments.
   Use `--view runtime` or `--view core --include-code-facts` when the chart
   must show implementation flow without proof-only labels or branches.
1. For target-critical equation sections, consume
   the current generated StableHLO and Lean evidence artifacts. Missing
   required evidence is an extraction or code-shape issue, not a reason to
   hand-maintain proof prose.
1. Propositionize theorem-critical equations from the current target
   proposition `P`, where `P` is stated over public-root return projections.
   Select the target theorem/profile in the theorem graph to bound the search
   surface, then trace the `Answer` / `State` / `Info` field paths to static
   return leaf indexes before following generated evidence/code graph records
   and backend phase records that `P` consumes. Runtime
   observation, diagnostic, and logging paths are not hard-coded as excluded or
   included: they enter the theorem graph only when `P` is about their validity
   or when their values are assigned into the value named by `P`. Otherwise they
   remain execution evidence outside the target
   substitution tree. IR fact extraction tells which equations are present;
   target proposition-tree search tells which of those equations matter for the
   current theorem. The skill must still explore which proposition states the
   useful mathematical guarantee. Do not freeze on the first bridge shape.
   Generate multiple bridge candidates at the abstraction level required by the
   target theorem, check or refute them when possible, and classify each
   candidate before choosing the next proof route. Do not leave
   theorem-critical returned values unconstrained when the current IR contains
   equations that determine or bound them.
   Interpret the result as a directed proposition graph.  Before accepting an
   algorithmic proof route, run the proof-path analyzer in leaf-origin mode and
   require every terminal leaf on the target chain to be a code function/fact,
   an analyzed top-level argument (`Problem`, `InitializeConfig`, `SolveConfig`,
   etc.), a backend/environment profile, or an explicit external library axiom.
   A graph that ends in free prose or an unrooted helper theorem is not evidence
   about the implemented algorithm.
1. Drive candidate selection recursively from the final theorem, not from a
   flat list. State the current target proposition `P`, run the checker/tactic
   search (`aesop?`, `aesop`, `simp?`, `exact?`, or the route selected by
   `$formal-proof-workflow`), record the unsolved subgoals or missing
   hypotheses, translate each missing item into candidate bridge propositions,
   check whether current Lean functions / generated IR facts can prove or
   refute those candidates, then rerun the target proof. Repeat until `P` is
   proved, refuted, shown unprovable under the current top-level assumptions, or
   reduced to a strictly smaller named witness.
   When a candidate condition proves `P` only because it is definitionally the
   same predicate as `P`, classify it as `projection_only` /
   `circularity_check`. Do not treat that candidate as an algorithmic success or
   a `Problem` condition. The algorithm frontier must instead move to the
   non-circular mechanism that would make `P` true, such as residual
   reachability for the implemented recurrence, a finite ranking function, a
   contraction/decrease lemma, or a problem-class witness that implies the
   projected stopping scalar.
   Run this circularity check on the theorem graph, not on names or vocabulary.
   A route remains circular if the proposition graph connects the conclusion
   side back to the candidate condition through definition, projection,
   equivalence, existential-lift, or certificate-inclusion edges. Do not accept a
   necessary/sufficient problem class merely because the terms were renamed or
   the proof did not close by a single definitional step.
1. For theorem-critical intermediate formulas, use
   `python3 tools/agent_tools/jit_canonical_ir.py` after theorem graph
   generation. Check assignment and return equations per iteration unit
   (`source_symbol` plus `equation_tags`, such as `step_update` or
   `reduced_kkt`) before handing them to `$formal-proof-workflow`. If the
   correspondence checker reports a missing graph node or consumption edge,
   fix IR extraction or graph generation instead of hard-coding prose equations.
1. Treat the theorem graph as the editable algorithm exploration surface. Agents
   and humans may add candidate algorithm changes, certificate edges, source
   packets, and formal-proof handoff decisions as overlay data, but must not
   hand-edit generated IR facts into a proof result.
   Structural analysis must distinguish projection evidence from numerical
   progress evidence. A theorem graph path that goes
   `Condition := Target -> Target` is connected but circular; it is kept as
   `circularity_check` and excluded from certified convergence / finite-stop
   subgraphs until a separate non-circular edge derives the condition from
   `Problem`, config, generated code facts, backend profile, or a formal-library
   theorem.
   The exclusion is graph-based: start from the target/conclusion node, follow
   proof-consumption edges, and reject the route if that path reaches the node
   being proposed as an independent problem class or certificate. Vocabulary
   checks are not sufficient evidence of non-circularity.
1. Extract an algorithm frontier from the graph, not from prose order. Pick
   target-facing blockers by algorithmic impact and reduce each to one of:
   implementation identity, returned-value projection, numerical
   reachability/ranking mechanism, algorithmic choice, external assumption
   binding, or problem-class witness.
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
   changing the algorithmic recurrence, deriving a numerical convergence
   witness, narrowing the problem class, or leaving an external assumption
   boundary.
1. Function-level blockers must be reported as a causal chain, not as a flat
   missing-lemma inventory.  For each recursive function on the target path,
   state `function`, `unguaranteed property`, `why that output can be wrong or
   insufficient`, `which caller-side lemma becomes unprovable`, and `which
   target theorem edge fails`.  Example shape:
   `<inner_solver> cannot guarantee requested residual for the current
   transformed operator -> <caller_solver> cannot bound returned direction
   error -> <outer_step> cannot prove the target residual/certificate property
   -> finite reachability remains unproved`.  If a function calls another
   function, recursively expand the callee until the gap is a problem/config
   witness, backend semantics boundary, or algorithmic choice.  Do not stop at
   "solver precision unverified" when a caller-visible output and failed
   downstream lemma can be named.
   A callee name is never itself the algorithmic blocker. Before reporting an
   algorithmic blocker, expand the callee's generated equations into the
   smallest relevant function predicates: input/output relation, return
   binding, loop-exit reason, stopping predicate, breakdown or exception
   predicate, and nested solver or callback output relation. Only after those
   predicates are verified, refuted, proved unprovable under the current
   top-level assumptions, or reduced to an external backend boundary may the
   blocker be returned.
   Distinguish `guarantee_unconnected` from `guarantee_refuted`.
   `guarantee_unconnected` means the current IR / Lean function path has not
   yet proved the property; it is a work queue.  `guarantee_refuted` means a
   checker-backed theorem, counterexample, model, or implementation trace shows
   the property is false for the current top-level assumptions and code path.
   Do not write "cannot guarantee" as a terminal blocker unless the refutation
   is checked.  If the returned blocker says a function cannot provide a
   guarantee, include the exact refutation theorem or model and prove that this
   missing function guarantee makes the caller-side lemma and target theorem
   edge fail.
   A local or partial counterexample must also be proven reachable from the
   public target trace before it can be used as `guarantee_refuted`.  Prove the
   top-level embedding theorem from the current `main` / run path, target
   `Problem`, config, and backend assumptions to the local counterexample
   input, then prove propagation to the caller lemma and target edge.  Without
   those two checker-backed edges, keep the artifact as
   `local_counterexample_candidate` or
   `route_rejected_not_top_level_reachable` and continue recursive frontier
   exploration instead of returning it to the user.
   Do not return user-facing progress with a function guarantee still marked
   `guarantee_unconnected` when that unconnected guarantee is the reason a
   caller-side lemma or target theorem edge is open.  Re-enter the recursive
   function frontier immediately: generate the next callee/function property,
   prove it, refute it, prove it unprovable under the current top-level
   assumptions, or change the algorithm and regenerate IR/graphs.  A smaller
   named witness is not a user-facing stopping point for this class of gap; it
   is the next in-turn work item.
   Apply the same rule to `connection_unconnected`: bridge edges, profile
   bindings, unit conversions, return-value substitutions, and
   theorem-variable instantiations must be recursively expanded before
   reporting progress. Only a checked code/input/backend boundary may be
   returned.
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
   upper-bound lemmas, selected-scope bounds, finite-prefix ranking/contraction
   witnesses, same-units conversion, or projection of existing algorithm return
   facts. Do not promote the desired condition into an independent
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
1. For iterative numerical algorithms, target the public-root return theorem
   first, then decompose it to the implemented recurrence and stopping scalar:
   `z_next = Step_impl(Problem, Config, z)` and
   `R_impl(Problem, Config, z)`. Prove contraction, ranking, finite
   reachability, or stopping soundness for that implemented map only as a local
   lemma needed by the `main` return theorem. Do not add runtime proof checks,
   proof-only `Info` fields, diagnostic gates, or proof-only config/state just
   to satisfy a proof obligation.
1. When the code must change for provability, state the algorithm change in
   proof terms first: remove an unsound gate, change the blocking recurrence,
   initializer, line search, inner-solver policy, regularization, Phase I /
   globalization route, narrow to a local theorem, or add a problem-class
   witness. A code change for provability means replacing the algorithm with a
   provable numerical mechanism, not embedding the proof check in production
   code.
1. Do not treat frontier classification or algorithm-change guidance as the
   skill completion condition. Completion requires a checker-backed result for
   the target theorem itself: either the target theorem is proved, or it is
   proved that the current assumptions and implementation path are insufficient
   to derive that theorem.
1. Treat `unverified_with_next_witness` as a handoff queue back to
   `$formal-proof-workflow`, not as algorithmic completion. Re-enter that named
   witness until the proof workflow returns `verified`, `refuted`,
   `unprovable_under_assumptions`, or a strictly smaller frontier witness.
   If the strictly smaller witness is another function-level guarantee whose
   absence blocks a caller lemma or target edge, do not return it to the user;
   continue the same recursion until that function guarantee is terminal or no
   repository/code/tool action can advance it.
1. If an algorithm change is needed, continue until either the current
   assumptions are proved insufficient or the changed algorithm has a
   checker-backed proof of the target theorem. A proposed change alone is only
   `algorithm_change_guidance`.
1. Do not add proof-only fields to production `InitializeConfig` or algorithm
   state. Proof-only backend profiles and theorem variables belong in
   `lean/lib/`, JIT-canonical IR, or graph overlays.
1. If the current implementation map is refuted or insufficient, regenerate IR,
   Lean code graph artifacts, theorem graphs, and proof-status overlays after the
   algorithm change and re-enter the same target theorem.
1. Store checker-facing IR, theorem graphs, proof overlays, and Lean stubs under
   `lean/<proof-theme>/`. Store reader-facing mathematical proof notes under
   `notes/themes/`.
1. Before reporting progress, run the current theorem graph checker against the
   theorem graph, proof status overlay, frontier/handoff artifact, and proof
   note. A valid connected path is structure evidence, not proof completion.
1. Hand terminal proof obligations to `$formal-proof-workflow`: checked theorem
   statements, counterexamples, unprovable-under-assumptions witnesses, existing
   proof search packets, checker commands, and the complete `Target Binding Packet`.

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
- `algorithm_change_guidance`: algorithmic changes needed to make a theorem
  provable without adding runtime proof-only surfaces.
- `formal_proof_handoff`: exact claims and artifacts for
  `$formal-proof-workflow`.
