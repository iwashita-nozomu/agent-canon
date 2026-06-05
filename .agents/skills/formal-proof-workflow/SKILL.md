---
name: formal-proof-workflow
description: Use when natural-language mathematical claims, Python AST-derived implementation claims, proof sketches, or theory assumptions should be converted into formal-proof obligations, existing-proof search packets, proof-assistant stubs, and checker-gated evidence.
---
<!--
@dependency-start
responsibility Exposes formal-proof-workflow to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/formal-proof-workflow.md canonical skill document
upstream implementation ../../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts
upstream implementation ../../../tools/agent_tools/proof_path_analyzer.py checks proof-status overlays against lemma graphs
upstream design ../../../agents/skills/literature-survey.md source search policy
@dependency-end
-->

# Formal Proof Workflow

1. Read `agents/skills/formal-proof-workflow.md`.
1. Read `agents/skills/literature-survey.md` before web or paper search.
1. Split the natural-language claim into assumptions, definitions, target theorem, proof sketch, and proof obligations; for implementation-derived claims, use `--python-symbol path.py::qualname` to extract side-effect-free AST provenance first.
1. Treat the terminal goal as either proving the target claim or proving that
   the target cannot be established from the current assumptions and
   implementation path. `blocked`, `not_run`, and `unverified` are intermediate
   states, not completion.
1. For algorithm-derived claims, mechanically and recursively expand the root algorithm into an Algorithm Expansion IR before selecting local proof obligations. The IR is not a proof; it is the intermediate representation used to choose only the local theorems needed by the final target.
1. Build that IR with `python3 tools/agent_tools/algorithm_expansion_ir.py --python-symbol <path.py::qualname> --target-theorem <target> --format json|markdown`, and retain `proof_algorithm_ir`, `proof_goal_directed_slice`, and `proof_selected_local_obligations` in the proof artifact.
   Do not add a caller-chosen recursion-depth knob to ordinary proof runs; the
   IR expands to saturation over AST-resolved calls and stops by already-seen
   `path.py::qualname` keys.
1. For implementation algebra, use IR `code_facts` before writing prose-only
   claims. Reduced-KKT equations, step updates, floor-preserving formulas,
   initialization-path facts, and solver defaults should be represented as
   code-derived facts and connected to lemma graph nodes before they are cited
   in a proof status table.
1. Keep backend / dtype / IREE / finite-precision semantics as Algorithm Expansion IR `backend_assumptions` and Lemma Dependency Graph overlay variables. Do not add proof-only backend fields to production `InitializeConfig` or algorithm state.
1. Store checker-facing IR, lemma graphs, profile libraries, and Lean stubs under `lean/<proof-theme>/`; store reusable proof profiles under `lean/lib/`. Proof tools such as `algorithm_expansion_ir.py` read those profile libraries; production algorithms do not. Keep reader-facing proof text in `notes/themes/`.
1. Convert Algorithm Expansion IR into a Lemma Dependency Graph with
   `python3 tools/agent_tools/algorithm_lemma_graph.py --target-profile <profile> --format json|markdown`.
   Retain `proof_lemma_graph`, `proof_target_chains`, and graph validation
   evidence before writing proof text.
1. After a proof-status overlay exists, run
   `python3 tools/agent_tools/proof_path_analyzer.py --lemma-graph <graph.json> --proof-status <proof_status.json> --proof-frontier <frontier.md> --adoption-text <proof-note.md>`
   before claiming proof-path progress. Treat `validation.valid=true` as
   evidence that the proof path is structurally connected and the remaining
   holes are named; treat `proof_complete=false` as the normal state while open
   witnesses or unprovable-under-assumption rows remain.
1. Treat the Lemma Dependency Graph as an editable proof-search surface.
   Keep IR-backed obligation nodes synchronized only by regenerating IR after
   source-program changes; add agent/human auxiliary lemmas, bridge edges,
   proof attempts, adoption decisions, and missing frontier as graph overlay.
   A reader-facing `verified` claim requires a checker-backed certified
   subgraph, not merely a candidate proof path.
1. Advance proof exploration from the frontier, not from prose order:
   choose the next target-chain node with no certified incoming proof, reduce it
   to the weakest local proposition that would advance the final theorem, and
   immediately classify the attempt as one of `verified`, `refuted`,
   `unprovable_under_assumptions`, or `unverified_with_next_witness`.
   Bare `unverified` may describe a raw generated node or stub, but it is not a
   completed frontier outcome.
1. For every unverified frontier node, try these routes in order:
   (a) prove the exact implementation algebra or certificate projection;
   (b) prove a conditional bridge theorem with explicit theorem variables;
   (c) refute an over-strong route with a concrete counterexample/model; or
   (d) prove that the current assumptions do not entail the target and name the
   missing witness. Do not leave a node as merely "hard" when a weaker terminal
   result can be checked.
1. When a node remains open, record the algorithm change that would make it
   provable: expose a runtime certificate, strengthen an acceptance contract,
   add a problem-class witness, narrow the theorem, or add a globalization /
   Phase-I route. Keep this as proof guidance, not as a proof-only production
   field.
1. Recursively re-enter the frontier loop on every named
   `unverified_with_next_witness` item until it is verified, refuted, proved
   unprovable under the current assumptions, or explicitly remains open with a
   smaller named witness. Do not close out a proof note with an open frontier
   row whose remaining obligation is empty or only says "unverified".
1. Run `python3 tools/agent_tools/formal_proof.py` to generate the proof plan, target-language scaffold, existing-proof queries, and literature queries.
1. Use a writing skill when producing reader-facing proof text: `$academic-writing` for symbol-dense proof notes, `$long-form-writing` for long guide/note form, and `$report-writing` for checker-evidence or audit summaries.
1. Keep each proof topic's theorem target, assumptions, checked fragments, and remaining gaps in one canonical proof note whenever possible; implementation code-path explanation may live in Design docs, but the proof note must link that Design entry and the mathematical proof text must not be split across competing truth surfaces.
1. Require a proof status table in every reader-facing proof note, with claim/theorem, implementation surface, `verified|refuted|unprovable_under_assumptions|unverified_with_next_witness|unverified|not_run|blocked`, checker evidence, and remaining obligation columns; do not hide proof status in prose.
1. When an algorithm module owns nested initialization through `initialize(config: InitializeConfig)`, use that initialize/config pair only to expand the required independent proof scopes. Do not make `initialize` itself a mathematical proof premise.
1. Search local repo sources, `references/`, `notes/`, and `documents/` before external web search.
1. Search existing formal proofs in the target ecosystem before creating new lemmas. For Lean/mathlib include docs, LeanSearch/Loogle/Moogle-style tools, Zulip archive, and in-editor tactic search when available. For Isabelle include AFP and Sledgehammer reconstruction evidence. For Coq/Rocq include library search and CoqHammer-related routes.
1. Use `$literature-survey` for external papers, official docs, source packets, adoption/exclusion reasons, and contrary or narrowing evidence.
1. Do not mark a claim verified unless the target proof assistant or solver checks the exact artifact without placeholders, `sorry`, `Admitted`, unchecked axioms, or equivalent proof escape hatches.
1. Do not mark a claim impossible merely because attempts failed. Use
   `refuted` only with a counterexample, formal model, or implementation trace
   falsifying the target conclusion; use `unprovable_under_assumptions` only
   with a checked independence result or a model / witness showing that the
   assumptions do not entail the target claim.
1. When a checked fragment is adopted, register it in the package-retained proof trace with consumed fragments, checker command, and any remaining implementation-instantiation obligations instead of hiding those boundaries in prose.
1. For implementation-derived proof traces, run `python3 tools/agent_tools/check_proof_trace_alignment.py --trace-module <trace.py>` before proof expansion or verified-status claims, and fix stale source paths, AST anchors, retained theorem names, and required/forbidden source-token drift first.
1. If the checker cannot be run, record `proof_status=not_run`, the exact command, and the missing environment or dependency.

## Algorithm Expansion IR

Use this pattern before proving implementation-derived algorithm claims.

1. Select the root from the public algorithm entrypoint consumed by the target theorem: `initialize`, `solve`, `step`, or a certificate-returning function.
1. Expand AST source, `InitializeConfig` ownership, nested solver selection, state updates, certificate projection, and diagnostic construction into nodes and edges without importing or executing the target module.
   Expansion is saturated over AST-resolved calls; do not tune a proof result
   by changing a recursion-depth parameter.
1. Classify nodes as mathematical state transition, linear/nonlinear solve, certificate, stopping predicate, diagnostic, performance-only helper, or implementation bookkeeping.
1. Preserve AST-derived assignment, return, module-constant, and class-default
   facts as `code_facts`. Use these facts to cite exact equations and defaults;
   do not downgrade such facts to prose or broad `code_symbol` anchors.
1. Backward-slice the IR from the final theorem. Keep selected local obligations and assumptions that are necessary for the final claim; exclude helper structure, type facts, and convenience fields that do not affect that claim.
   Discharge instance method dispatch and constructor binding as `static_checks`
   before proof selection. Do not include dispatch edges in proof obligations;
   keep only the callee theorem or child proof scope when it is mathematically
   relevant.
   Expand visible function-pointer variants such as `self.update(...)` into
   same-module variant functions before proof selection; keep variant selection
   as a static dispatch check and the variant math as ordinary nodes.
1. Put backend arithmetic, IREE FP32, fast-math, denormal, and lowered-IR assumptions in IR `backend_assumptions`; treat them as theorem variables or witness obligations.
1. Assign each selected obligation to a formal theorem, existing-proof search, literature evidence, or explicit problem-class/backend assumption.

## Lemma Dependency Graph

Use this after Algorithm Expansion IR and before writing proof text.

1. Store auxiliary lemmas, assumptions, and target theorem/profile nodes as a graph.
1. Use IR `node_id`, not implementation symbol alone, as the lemma identity.
1. Connect `code_facts` as graph nodes when they are consumed by the proof
   path. Connect backend profile records from `lean/lib/` as graph nodes under
   backend assumptions; production algorithms must not read those proof
   profiles.
1. Treat generated graph output as the initial graph. Agents and humans may
   edit the overlay by adding auxiliary lemmas, bridge lemmas, dependency
   edges, proof attempts, failed routes, adoption decisions, and missing
   frontier entries.
1. Do not hand-edit IR-backed obligation nodes to remove or rename them. If
   the source program changes, regenerate the IR. If a node is irrelevant to
   the current proof path, leave it in the graph and exclude it from the active
   target chain, certified subgraph, or missing frontier.
1. Keep multiple target profiles for one algorithm, such as `certificate_soundness`,
   `local_convergence`, `fp32_floor`, and `solver_chain`.
1. Require graph validation for edge endpoints, acyclicity, and target-chain
   reachability before making reader-facing proof claims.
1. Run `proof_path_analyzer.py` on the lemma graph, `proof_status.json`, and
   proof frontier/note before every reader-facing progress claim. It should
   fail on missing graph endpoints, disconnected target chains, unadopted
   checked fragments, stale implementation tokens, bare `unverified` frontier
   rows, or duplicate frontier labels.
1. Proof paths are Try-and-Error artifacts. Keep failed or blocked attempts in
   the overlay, but certify only the subgraph whose lemma nodes and dependency
   edges have checker evidence.
1. Static dispatch, import binding, callbacks, and function-pointer variants may
   create dependency edges, but their structural facts are not mathematical
   lemmas.

## Frontier Exploration Loop

Use this loop after graph generation and before claiming progress on an
algorithm theorem.

1. Pick a target theorem/profile and compute its uncertified frontier from the
   lemma graph. Prefer nodes whose proof would unlock multiple downstream
   edges, but do not skip a refutable over-strong claim.
1. Normalize each selected node into one of four proposition shapes:
   exact implementation identity, conditional bridge, reachability/existence
   statement, or external assumption binding.
1. Attempt a checker-backed result for the normalized proposition:
   - `verified`: the proposition is proved by a checker with no escape hatches.
   - `refuted`: a checker-backed counterexample/model falsifies the proposition.
   - `unprovable_under_assumptions`: a checker-backed witness shows the current
     assumptions do not entail the proposition.
   - `unverified_with_next_witness`: the exact missing theorem variable,
     runtime certificate, backend evidence, or problem-class witness is named.
      Immediately re-enter this same loop on that witness or next frontier.
1. If a weaker proposition is verified, add a bridge edge showing what remains
   to use it in the target theorem. If a stronger route is refuted, keep the
   refutation and replace the route with a narrowed theorem or algorithm change.
1. Update the proof status table and proof note in the same pass. Every open
   row must state whether the next step is mathematical proof, implementation
   certificate plumbing, backend evidence binding, or theorem narrowing.
   Do not close out while a frontier row still has bare `unverified` as its
   only outcome.

## Initialize-Rooted Proof Expansion

Use this as one edge family inside the Algorithm Expansion IR when a runtime
module recursively initializes lower solvers, stopping predicates, or
preconditioners.

1. Record `root_initialize` and `root_config_type`, such as
   `pdipm.initialize` with `pdipm.InitializeConfig`, or standalone
   `minres.initialize` with `minres.InitializeConfig`.
1. For each child `InitializeConfig` field, record an expansion edge with
   `child_config_field`, `child_initialize`, `proof_scope`, `selection_rule`,
   and `role`.
1. Keep the proof itself independent. The expansion graph selects which
   independent proof scope is required; it is not a theorem and does not prove
   the selected scope.
1. If a method or algorithm family can change, choose a different proof scope
   through a method/variant registry. Do not rewrite the caller theorem to
   encode one lower method.
1. For standalone solver use, start at that solver's own `initialize`; do not
   pull in parent optimizer or KKT proof scopes.
1. Keep expansion edges separate from proof dependency edges. Expansion edges
   describe runtime ownership; proof dependency edges describe theorem/lemma
   consumption.
1. Do not add proof-only config or proof-only state. Values needed only by the
   proof stay as theorem variables or problem-class/backend assumptions.

## Nested Iterative Solver Proofs

Use this pattern when an outer algorithm depends on an inner iterative solver.

1. Index every quantity by the outer iteration. Do not replace dynamic
   conditioning, scaling, or required accuracy by one global constant unless the
   proof explicitly proves a uniform bound over the local tube.
1. Start from the outer recurrence requirement and derive the inner requested
   residual budget. For a direction error premise, prove a theorem of the form
   `effective_residual_budget_k <= requested_residual_budget_k -> direction_error_k <= requested_direction_error_k`.
1. Split dynamic gains into implementation-owned factors. For reduced KKT
   systems, keep at least reduced inverse gain, back-substitution gain, scaling
   or floor-model gap, and backend arithmetic floor as separate premises.
1. Nest solver obligations in dependency order: outer recurrence request,
   reduced-system residual request, Krylov solver true-residual certificate,
   preconditioner spectral/norm-conversion certificate, and backend residual
   reconstruction floor.
1. Keep inner-solver lemmas parametric in quantities that only the caller can
   determine, such as dynamic gains, requested residual budgets, selected
   tolerances, and problem/current-state regularity witnesses. Add a top-level
   substitution lemma for the caller instead of computing those values in the
   lower proof.
1. Treat preconditioners as part of the inner solver certificate, not as an
   outer proof shortcut. If a preconditioned residual is reported, prove the
   norm-conversion bound back to the outer residual units before using it.
   If the implementation recomputes and returns a physical true residual, keep
   preconditioner quality in the reachability proof for attaining that residual,
   not as an extra term in the returned residual budget.
1. Expose runtime witnesses on existing algorithm `Info` or diagnostic surfaces
   only when they are execution facts. Do not add proof-only config or proof-only
   state to satisfy a proof obligation.
1. Record unresolved items as problem-class or backend assumptions with concrete
   names and units, such as `local_reduced_kkt_inverse_gain_k`,
   `backsubstitution_gain_k`, `preconditioned_to_physical_residual_gain_k`, and
   `fp32_backend_floor_k`.
