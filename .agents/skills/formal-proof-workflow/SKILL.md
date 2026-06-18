---
name: formal-proof-workflow
description: Use when natural-language mathematical claims, JIT-canonical implementation claims, proof sketches, or theory assumptions should be converted into formal-proof obligations, generated Lean evidence, theorem-graph targets, and checker-gated evidence.
---

<!--
@dependency-start
responsibility Exposes formal-proof-workflow to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/formal-proof-workflow.md canonical skill document
upstream design ../../../agents/skills/algorithm-proof-exploration.md proof-guided algorithm exploration workflow
upstream implementation ../../../tools/agent_tools/lean_proof_env.py creates Lean proof-search, theorem-search, and counterexample environments
upstream design ../../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop/Plausible/LeanSearchClient capabilities by proof-frontier shape
upstream implementation ../../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived thin operational IR and backend traces
upstream implementation ../../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules
upstream design ../../../agents/skills/literature-survey.md source search policy
@dependency-end
-->

# Formal Proof Workflow

1. Read `agents/skills/formal-proof-workflow.md`.
1. Read `agents/skills/literature-survey.md` before web or paper search.
1. For algorithm-derived claims that require proof-path search, algorithm
   comparison, or code changes for provability, also use
   `$algorithm-proof-exploration` before final proof adoption.
1. Split the natural-language claim into assumptions, definitions, target theorem, proof sketch, and proof obligations. For implementation-derived claims, use the JIT-canonical public root consumed by the theorem.
1. Run `python3 tools/agent_tools/formal_proof.py` to generate the proof plan,
   target-language scaffold, existing formal proofs search packet, and
   literature queries before adopting theorem text or proof obligations.
1. For implementation-derived algorithm proofs, always start from the whole
   target theorem over the JIT-canonical public entrypoint, normally the
   `main(problem, InitializeConfig, ...)` or equivalent run function and its
   returned `Answer` / `State` / `Info` specification. Do not begin from a
   helper lemma, inner solver claim, loop-control fact, residual component, or
   hand-selected local theorem unless it is selected by recursively decomposing
   that top-level main theorem.
1. For implementation-derived claims, fix a `program contract` before theorem
   text or reader-facing prose: public entrypoint, input schema, runtime
   profile, return projection, observable effect, assumptions / preconditions,
   and checker / validation command.
1. Build the theorem statement from the public root's static argument schema
   and return schema. The target theorem must talk about `let out := main
   problem config` and its returned `Answer` / `State` / `Info` fields, or
   generated high-level projections of those fields. Do not make low-level
   operation ids, bindings, regions, frames, trace rows, or the internal state
   of `generatedMainFuel` the theorem surface. Low-level generated evidence is
   used only to prove that those public projections follow the implementation
   path.
1. Keep proof-relevant public inputs in the JIT root signature. A proof root may
   take real runtime inputs such as `Problem`, `InitializeConfig`, and an
   actual runtime solve config when the API has one, but it must not add
   proof-only arguments, trace handles, op ids, binding ids, or proof-only
   state/config. If a theorem needs a value, expose it through the public return
   schema or reconstruct it in the theorem graph from the implementation path.
1. When handing proof work to a subagent, include the `Target Binding Packet` from
   `agents/COMMUNICATION_PROTOCOL.md`: exact target theorem, public root and
   signature, return projection, identifier naming plan, accepted top-level
   assumptions, forbidden assumptions, current generated evidence, completion
   condition, validation commands, and unchecked-output policy. Do not ask a
   subagent to "look at the proof" or "find blockers" from a file list alone.
   Do not adopt an unchecked theorem sketch, type-incompatible statement, local
   counterexample, or algorithm suggestion unless it is checked against the same
   public root and theorem surface.
1. Treat the terminal goal as either proving the target claim or proving that
   the target cannot be established from the current assumptions and
   implementation path. `blocked`, `not_run`, and `unverified` are intermediate
   states, not completion.
1. For algorithm-derived claims, consume the
   `$algorithm-proof-exploration` artifact when available. If it does not
   exist yet, lower the public root into JIT-canonical IR before selecting
   local proof obligations. The IR is not a proof; it records what the JIT root
   computes.
1. Build that IR with
   `python3 tools/agent_tools/jit_canonical_ir.py --python-symbol <path.py::qualname> --input-factory <path.py::qualname> --out <ir.json> --stablehlo-out <root.stablehlo.mlir> --backend-trace-dir <dir> --backend-trace-out <backend.json>`.
   Retain the StableHLO hash, thin operational ops, backend phase trace, and
   coverage status in the proof artifact. Do not add recursion-depth knobs or
   hand-written operation records.
   For CUDA finite-precision claims, also pass `--backend-target cuda`,
   `--iree-cuda-target <sm_xx>`, and `--xla-dump-dir <dir>` so the extractor
   can collect XLA-emitted `.ll` / `.ptx` artifacts when IREE phase tracing
   stops before LLVM. Treat missing LLVM rows as a backend coverage frontier,
   not as permission to introduce external FP axioms.
1. Generate checker-facing Lean evidence definitions from the current
   JIT-canonical IR with `tools/bin/agent-canon jit-ir-to-lean`. Keep this
   generated evidence layer separate from the theorem graph. The
   generated layer owns root identity, StableHLO hash, operational op kinds,
   dtype coverage, and backend trace coverage. Mathematical propositions such
   as residual decrease, KKT regularity, direction quality, and finite
   termination belong only in the theorem graph.
   Require the generated layer or theorem-graph projection layer to expose the
   public root argument tree, return tree, return leaf indexes, and high-level
   projection functions for theorem-visible return fields. If these projections
   are absent, fix extraction or the `main` return shape before proving local
   low-level facts.
1. Backend arithmetic is generated trace evidence, not an external backend
   axiom. If backend lowering stops before LLVM or executable code, record the
   last successful backend phase as a coverage gap and decide whether to fix
   the algorithm, the lowering path, or the backend configuration. If an
   alternate compiler-owned route such as XLA CUDA dump can emit LLVM for the
   same JIT root, collect that route in the backend trace and lower the
   resulting instruction list into Lean before reporting a backend frontier.
   Do not fix a backend, runtime target, compiler route, device, or dtype to
   make a theorem or validation claim pass. A backend-specific theorem is valid
   only when the user request, approved design, runtime profile, public API, or
   config explicitly scopes the theorem to that backend. Otherwise keep backend
   semantics as top-level profile input, generated backend witness, and coverage
   evidence. If evidence is missing, record `backend_evidence_blocker=<gap>`
   instead of narrowing the theorem to IREE, XLA, CUDA, CPU, GPU, VMFB,
   StableHLO, LLVM, FP32, or another backend surface.
   For target-critical code shape, do not leave implementation-local functions
   as arbitrary proof axioms merely because the first trace generator is shallow.
   Residual bundles, next-state construction, step-length formulas, KKT
   reconstruction, stopping residual aggregation, and other target-facing code
   path functions must be implemented as Lean functions whose fields correspond
   to the implementation data flow.  Use axioms only for explicit architecture
   or backend semantics boundaries, or for problem-owned analytic functions
   that are top-level theorem assumptions.  If an IR extraction cannot yet emit
   the needed function body, either improve the extractor or add a small
   checker-facing function with a dependency edge to the IR fact; do not return
   an arbitrary function axiom as a proof frontier.
   State implementation-derived theorems over the data types used by the
   implementation path, or over an explicit decoded view of those data types
   with a checked binding lemma.  Do not replace implementation residuals,
   statuses, solver answers, finite-precision values, or certificates by a
   convenient surrogate type such as `Nat`, `Real`, or an unconstrained record
   unless the code path already uses that type or a theorem proves the coercion,
   decode, unit conversion, or projection from the implementation type.  If the
   implementation uses finite precision, prove arithmetic claims over the
   rounded value model and `decode` relation consumed by the theorem, not over a
   field abstraction that the runtime values do not satisfy. Connect backend
   LLVM instruction evidence to theorem variables through a typed witness such
   as `BackendFloatWitness`, then consume reusable finite-precision lemmas such
   as `final_tolerance_survives_decoding_error`.
   For iterative numerical convergence claims, keep the whole-root public
   return theorem as the top-level target. The implemented recurrence and
   stopping scalar, such as `z_next = Step_impl(Problem, Config, z)` and
   `R_impl(Problem, Config, z)`, are local lemmas selected by decomposing that
   public-return theorem. Prove contraction, ranking, finite reachability, or
   stopping soundness for that implemented map only after the target theorem has
   been projected from `main`'s static return schema. Do not add runtime proof
   checks, proof-only `Info` fields, diagnostic gates, or proof-only
   config/state to make a theorem true. If the current map is checker-refuted or
   insufficient, return to `$algorithm-proof-exploration` to replace the
   initializer, update rule, line search, inner-solver policy, regularization,
   Phase I, or globalization route with a provable numerical mechanism, then
   regenerate IR and retry the theorem.
   For target-critical equations, start from the theorem proposition and trace
   to the generated JIT-canonical Lean evidence definitions and StableHLO/backend trace
   records it actually consumes. Do not hand-maintain parallel runtime
   equations in proof notes. If the theorem needs a formula not present in the
   generated implementation layer, improve the extractor or change the
   implementation shape before adopting the theorem.
   After extraction, propositionize theorem-critical equations from the target
   proposition, not from a flat op list. First select the target theorem/profile
   in the theorem graph to bound the search surface. The proposition must be
   stated over public return projections, then the substitution tree follows
   `Answer` / `State` / `Info` field paths to static return leaf indexes before
   it descends into local assignments and callee return equations. Generate
   bridge candidates only from facts in that projection-rooted tree.
   Runtime observation, diagnostic, or logging paths are not globally excluded:
   if `P` is about their validity, they are the tree root; if `P` is about a
   returned solver value and those paths are not assigned into that value, they
   remain execution evidence outside the substitution tree. Facts outside the
   selected theorem/profile, outside the proposition tree, or marked
   `substitution_eligible=false` are not first-class substitution
   propositions for `P`. Hand-translate target-tree equations into typed Lean
   propositions and bridge theorems. IR facts identify code equations; Lean
   propositions state possible mathematical meanings. Generate multiple bridge
   candidates at the abstraction level required by the target theorem, check or
   refute them when possible, and classify each candidate before choosing the
   route used by the final theorem. Do not leave theorem-critical returned
   values unconstrained when the current IR contains equations that determine
   or bound them.
   Candidate selection is recursive and target-driven: state the final
   proposition `P`, run the appropriate proof search (`aesop?`, `aesop`,
   `simp?`, `exact?`, or the Lean capability route), inspect the unsolved goals
   and missing hypotheses, generate bridge candidates for those exact gaps,
   prove/refute them from generated Lean functions and IR facts, then rerun the
   proof of `P`. A flat candidate inventory is only input to this loop, not the
   proof workflow outcome.
   Treat the theorem graph as a directed proposition graph:
   proposition nodes point to the propositions they consume.  For
   implementation-derived proofs, every terminal leaf on the target chain must
   be rooted in exactly one allowed origin class: a code function/code fact, an
   analyzed top-level function argument such as `Problem`, `InitializeConfig`, or
   `SolveConfig`, a backend/environment profile, or an explicit external library
   axiom. Run the theorem graph checker in leaf-origin mode before claiming a
   code-aligned proof. If a leaf is free prose, an unrooted helper theorem, or a
   proof-only assumption, remove that path or reconnect it to code/argument/
   backend evidence.
1. After any algorithm update that changes initialization, cold-start,
   Phase-I, basin-entry, or selected-scope-entry logic, regenerate the
   JIT-canonical IR, generated Lean operational-program evidence, theorem
   graphs, and proof-status overlay before reporting back.
   Discharge every initialization fact that the code now exposes as
   `generated implementation leaves` first: selected base point, epigraph point, slack/multiplier
   floors, initial residuals, and initial child-solver state. Do not return
   those as user-owned blockers when they can be extracted from the current
   implementation.
1. Normalize initialization proofs through a selected initializer
   `z_init = Init(Problem, InitializeConfig)`. Do not make `z_init = 0` a
   theorem premise unless the implementation path itself mathematically fixes
   zero and the IR code facts show that specialization. If a hard-coded zero or
   default vector is merely an algorithmic choice that blocks the theorem,
   route it back to `$algorithm-proof-exploration` as an algorithmic choice or
   problem-class witness.
1. For implementation-derived convergence claims, treat the implemented
   algorithm itself as an operational assumption: `trace follows A_impl / Step_impl` extracted from IR. Convergence, finite termination, residual
   reachability, and certificate soundness are derived lemmas, not assumptions.
   Record this premise under `operational_assumptions`, separate from
   `open_frontier` and `external_assumptions`.
1. Keep backend / dtype / IREE / finite-precision semantics as JIT-canonical IR `backend_trace` and theorem graph overlay variables. Do not add proof-only backend fields to production `InitializeConfig` or algorithm state.
   If the compiler/runtime semantics are outside the current proof theme, use an
   explicit generated backend trace coverage in `lean/lib` or the proof-theme Lean files
   instead of making IREE lowering, fast-math, denormal, or min/max semantics a
   blocker for the algorithm proof.
   Bridge, connection, profile binding, and witness instantiation rows are
   recursive proof frontier, not user-facing stopping points. If such a row
   blocks a caller-side lemma or target theorem edge, continue by expanding the
   code fact, generated Lean function, theorem graph, `lean/lib` profile, or
   backend/source packet that could bind it. Return only after the remaining
   gap is checked as a production code / algorithm issue, a top-level
   `Problem` / config / solve-input issue, or a backend/runtime architecture
   boundary that the current repository and tools cannot advance.
1. Keep runtime `Info` for runtime diagnostics, convergence checks, and logs
   only. Do not add proof-only witness fields to `Info`. Values needed by a
   proof should be reconstructed by the proof extractor or theorem graph from
   `Problem + InitializeConfig + State_k` and consumed through upper-bound
   lemmas such as `runtime_value <= upper_bound <= requested_budget`.
   Per-iteration KKT conditioning measurement is only one validation route;
   prefer a uniform selected-scope certificate for regularity, preconditioner quality,
   slack floors, and back-substitution bounds when it can specialize to every
   path state.
1. Ground every assumption in the target algorithm inputs before adopting it.
   For implementation-derived algorithm theorems, accepted non-code premises
   must be one of: properties of the target `Problem`, numeric choices in the
   target configuration object, an architecture assumption such as the
   IR-extracted operational trace or selected backend/runtime profile, or a
   formal-library theorem. A path state such as `State_k` may appear only as a
   value generated by that `Problem + Config` trace; it is not an injected
   assumption. Do not introduce assumptions about objects that are not target
   inputs, such as an arbitrary residual map, abstract direction, free selected
   scope, proof-only state, or diagnostic-only field. Intermediate claims are
   lemmas, not assumptions: classify them as problem/config-derived lemmas,
   prove them from the top-level assumptions plus the extracted code path, and
   do not promote them into newly injected premises.
   Rewrite those as lemmas/witnesses derived from `Problem + Config` and the
   generated path, or classify the stronger theorem as `refuted` /
   `unprovable_under_assumptions`.
   Algorithm-specific injected mathematical assumptions are limited to the target
   algorithm's public problem/input object and configuration object;
   implementation trace and backend/runtime semantics are architecture
   assumptions, not problem assumptions.
   For optimization problems, "differentiable" refers to the target `Problem`
   objective and constraint functions only; do not use differentiability of a
   residual sequence, update rule, or proof-introduced helper as a substitute.
1. Store checker-facing IR, theorem graphs, profile libraries, and generated Lean files under `lean/<proof-theme>/`; store reusable proof profiles under `lean/lib/`. Proof tools such as `jit_canonical_ir.py` read those profile libraries; production algorithms do not. Keep reader-facing proof text in `notes/themes/`.
1. Build the implementation layer with
   `python3 tools/agent_tools/jit_canonical_ir.py --python-symbol <path.py::qualname> --input-factory <path.py::qualname> --out <ir.json> --stablehlo-out <root.stablehlo.mlir> --backend-trace-dir <dir> --backend-trace-out <backend.json>`
   and then
   `tools/bin/agent-canon jit-ir-to-lean --jit-ir <ir.json> --namespace <Lean.Namespace> --module-name <name> --out <Generated.lean>`.
   Convert the generated implementation layer into theorem graph overlays with
   the current theorem-graph tool, not by passing theorem-profile options to
   `jit_canonical_ir.py`. Retain `proof_lemma_graph`,
   `proof_target_chains`, and graph validation evidence before writing proof
   text. After algorithm changes, regenerate IR, generated Lean evidence,
   theorem graphs, and proof-status overlays from the current root; do not carry
   old IR-backed generated lemma groups forward by fingerprint or prose edits.
1. If the task asks what iterative algorithm is implemented or where proof
   holes sit on the implementation path, use `$algorithm-flowchart` after IR,
   theorem graph, and proof-status generation. The chart is navigation evidence,
   not proof completion.
1. After a proof-status overlay exists, run the theorem-graph correspondence
   checker for the theorem-critical equation slice, especially `step_update`,
   `reduced_kkt`, `minres_defaults`, and initialization tags. This checker
   consumes the generated JIT-canonical IR / Lean operational-program evidence
   and validates variable-assignment and return-equation correspondence; it is
   distinct from mathematical proof completion. Do not call
   `jit_canonical_ir.py` with non-existent graph-checking options.
1. After equation correspondence is valid, run
   the theorem graph checker
   before claiming proof-path progress. Treat `validation.valid=true` as
   evidence that the proof path is structurally connected and the remaining
   holes are named; treat `proof_complete=false` as the normal state while open
   witnesses or unprovable-under-assumption rows remain.
1. Treat the theorem graph as an editable proof-search surface.
   Keep IR-backed obligation nodes synchronized only by regenerating IR after
   source-program changes; add agent/human auxiliary lemmas, bridge edges,
   proof attempts, adoption decisions, and missing frontier as graph overlay.
   A reader-facing `verified` claim requires a checker-backed certified
   subgraph, not merely a candidate proof path.
   The certified subgraph must also pass the leaf-origin check.  A proof path
   whose terminal leaves do not resolve to code, target arguments, backend
   environment, or external-library axioms is not a code verification path, even
   if the intermediate Lean theorem typechecks.
1. Propositionize the full target-facing algorithm route before returning an
   algorithmic blocker. For an iterative solver this means, at minimum, the
   stopping scalar, state update, step-length or acceptance selection,
   direction construction, nested solver return/certificate, residual or merit
   recomputation, and final scalar binding must each have theorem-specific Lean
   propositions or a checker-backed reason why the IR cannot expose them. A
   route fact such as "function A calls function B" is not enough when the
   target theorem depends on the value returned by B. Continue expanding until
   the remaining row is a semantic mechanism, such as a contraction theorem,
   residual-merit selection, problem-class analytic bound, backend boundary, or
   checker-backed refutation. Do not return a blocker while an unpropositionized
   generated equation on the target path could still determine the missing
   value.
1. Advance proof exploration from the frontier, not from prose order:
   choose the next target-chain node with no certified incoming proof, reduce it
   to the weakest local proposition that would advance the final theorem, and
   immediately classify the attempt as one of `verified`, `refuted`,
   `unprovable_under_assumptions`, or `unverified_with_next_witness`.
   Bare `unverified` may describe a raw generated node or unchecked generated file, but it is not a
   completed frontier outcome.
1. For every unverified frontier node, try these routes in order:
   (a) prove the exact implementation algebra or existing algorithm-output
   projection;
   (b) prove a conditional bridge theorem with explicit theorem variables;
   (c) refute an over-strong route with a concrete counterexample/model; or
   (d) prove that the current assumptions do not entail the target and name the
   missing witness. Do not leave a node as merely "hard" when a weaker terminal
   result can be checked.
1. When a node remains open, record the algorithm change that would make it
   provable: replace the current recurrence, initializer, line search,
   inner-solver policy, regularization, Phase I / globalization route, strengthen
   an acceptance rule as part of the algorithm, add a top-level problem-class
   witness, or narrow the theorem. Keep this as proof guidance, not as a reason
   to add proof-only fields, diagnostic gates, or runtime proof checks to
   production code.
1. Before returning a blocker to the user, show that it is frontier-minimal for
   the selected theorem/profile: all earlier target-chain nodes are terminal or
   adopted external assumptions, and the returned row has no smaller open
   target-chain witness underneath it. Include proof-path analyzer output,
   graph-slice evidence, or a checker-backed minimality lemma. Do not return a
   high-level "convergence/KKT is unproved" row when a smaller open witness is
   available.
1. Do not present route-specific sufficient witnesses, exploration candidates,
   or theorem variables as mathematically necessary assumptions unless a
   checker-backed necessity/refutation/minimality result establishes that
   status. Label them as `necessary_proven`, `route_sufficient`, `candidate`,
   `unknown`, or `algorithmic_blocker_proven`.
1. Recursively re-enter the frontier loop on every named
   `unverified_with_next_witness` item until it is verified, refuted, proved
   unprovable under the current assumptions, or explicitly remains open with a
   smaller named witness. Do not close out a proof note with an open frontier
   row whose remaining obligation is empty or only says "unverified".
   If the smaller named witness is a function-level guarantee whose absence is
   the stated reason a caller-side lemma or target theorem edge is open, do not
   return it to the user. Continue recursively until that function guarantee is
   verified, refuted, proved unprovable under the current assumptions, or
   reduced to an explicit external boundary that no available repository/code/
   tool action can advance.
   If the named witness points to a callee function, do not return the function
   name as a blocker. Expand that callee's implementation-derived input/output
   relation, return binding, loop-exit condition, stopping predicate,
   breakdown or exception predicate, and nested solver or callback return
   values until the caller-needed property is reduced to a Lean proposition or
   checker-backed countermodel. A bare "callee quality unproved" row is not a
   terminal outcome.
1. When the user asks to run, prove, or show the theorem, treat
   `unverified_with_next_witness` as an in-turn work queue, not as a
   user-facing terminal result. Each frontier row must end as `verified`,
   `refuted`, `unprovable_under_assumptions`, or be replaced by a strictly
   smaller named frontier witness that is immediately re-entered into the same
   loop.
1. "No proof path works" means no path under the current Algorithm Expansion
   IR, assumption ledger, and adopted generated backend trace coverage gaps. Support that claim with
   a checker-backed countermodel, independence result, or obligation-gap model;
   failed attempts and "hard" are not outcomes.
1. If a named witness can be derived from repository code, existing proof
   libraries, official source packets, local run artifacts, or checker output,
   implement the capture/checker/proof-note update before returning progress to
   the user. Return only when the witness genuinely depends on user-owned
   external runs, unavailable tools/authority, or a deliberate external
   semantics axiom; classify that boundary explicitly as `external_assumption`
   or with a strictly smaller `next_witness`.
1. If the next lemma, bridge, connection, or witness needed by the target chain
   is already known, do not report it as future work. Generate it, propositionize
   it, run the checker, and update the proof-status artifact in the same turn.
   Only return when that witness is verified, refuted, proved unprovable under
   the current top-level inputs, or reduced to a strictly smaller checked
   frontier that cannot be derived from local code/tool/library evidence.
1. Before returning user-facing progress, finish every currently selected
   component proof attempt to a terminal or smaller-frontier state. Each
   component must be `verified`, `refuted`, `unprovable_under_assumptions`, or
   `unverified_with_next_witness` with a strictly smaller named witness; do not
   return after only unchecked generated files or a bare list of unproved
   items.
1. If the target claim is not terminal when reporting to the user, return a
   nonterminal proof packet, not a thin "unproved" summary. Include: exact
   target claim, current outcome, strongest checked fragments with checker
   commands, failed/rejected routes, remaining named witnesses, witness owner
   (`problem_class`, `implementation`, `backend`, `formal_library`, or
   `algorithm_exploration`), evidence paths, and exact next action. For
   `refuted`, include the counterexample/model/trace; for
   `unprovable_under_assumptions`, include the witness/model showing current
   assumptions do not entail the target.
1. Use a writing skill when producing reader-facing proof text: `$academic-writing` for symbol-dense proof notes, `$long-form-writing` for long guide/note form, and `$report-writing` for checker-evidence or audit summaries.
1. Keep each proof topic's theorem target, assumptions, checked fragments, and remaining gaps in one canonical proof note whenever possible; implementation code-path explanation may live in Design docs, but the proof note must link that Design entry and the mathematical proof text must not be split across competing truth surfaces.
1. Require a proof status table in every reader-facing proof note, with claim/theorem, implementation surface, `verified|refuted|unprovable_under_assumptions|unverified_with_next_witness|unverified|not_run|blocked`, checker evidence, and remaining obligation columns; do not hide proof status in prose.
1. When an algorithm module owns nested initialization through `initialize(config: InitializeConfig)`, use that initialize/config pair only to expand the required independent proof scopes. Do not make `initialize` itself a mathematical proof premise.
1. Search local repo sources, `references/`, `notes/`, and `documents/` before external web search.
1. Search existing formal proofs in the target ecosystem before creating new lemmas. For Lean, read `documents/tools/lean_capability_matrix.md` and route each frontier by shape: direct equations through `rfl`/`rw`/`simp`/`simpa`; structural goals through `constructor`/`cases`/`use`/`aesop?`/`aesop`; Nat/Int arithmetic through `omega` and focused `grind`; ordered linear arithmetic through `linarith`; polynomial recurrence through `ring_nf` and `nlinarith`; positivity/monotonicity through `positivity` and `gcongr`; theorem discovery through `exact?`/`apply?`/`rw?`/`simp?`, Mathlib docs, LeanSearch, Loogle, LeanSearchClient, and Moogle-style tools; over-strong executable claims through Plausible counterexample probes. For active proof themes, pin Mathlib/Aesop/Plausible/LeanSearchClient once in the topic-local Lake package so ordinary retries use `lake build`; use `python3 tools/agent_tools/lean_proof_env.py all-smoke|smoke|agent-smoke|counterexample-smoke|check-file --env-dir reports/formal-proof/lean-proof-env` for exploratory or fallback environment checks. For Isabelle include AFP and Sledgehammer reconstruction evidence. For Coq/Rocq include library search and CoqHammer-related routes.
1. Use `$literature-survey` for external papers, official docs, source packets, adoption/exclusion reasons, and contrary or narrowing evidence.
1. Do not mark a claim verified unless the target proof assistant or solver checks the exact artifact without placeholders, `sorry`, `Admitted`, unchecked axioms, or equivalent proof escape hatches.
1. Do not mark a claim impossible merely because attempts failed. Use
   `refuted` only with a counterexample, formal model, or implementation trace
   falsifying the target conclusion; use `unprovable_under_assumptions` only
   with a checked independence result or a model / witness showing that the
   assumptions do not entail the target claim.
1. For implementation-derived claims, a helper-level, component-level,
   residual-slice, or otherwise partial counterexample is not a user-facing
   `refuted` result until it is embedded into the top-level public theorem
   trace.  Before returning or adopting that counterexample, prove a
   reachability/instantiation theorem showing that the current top-level
   `Problem` / config / backend assumptions and JIT-canonical `main` or run
   path can produce the local state, input, model, or trace used by the
   counterexample, and prove the propagation edge from the local falsified
   property to the target theorem conclusion.  If either edge is missing,
   classify the artifact as `local_counterexample_candidate` or
   `route_rejected_not_top_level_reachable`, keep it in the failed-route
   overlay, and continue the target-rooted frontier search.  Do not report it
   as terminal refutation or unprovability.
1. For a function-level guarantee, separate "not yet derived" from
   "cannot be guaranteed".  If the proof packet says a function cannot
   guarantee a property, formalize the property over that function's
   implementation-derived input/output relation and prove one of:
   a checked counterexample/trace falsifies the property, or a checked model
   satisfies the current top-level assumptions while falsifying the property.
   Then prove the propagation edge showing that this failed function guarantee
   prevents the caller-side lemma and target theorem edge from being
   established.  Without that refutation, report the row as
   `unverified_with_next_witness`, not as a terminal blocker.
   A function guarantee row whose status is `guarantee_unconnected` is not
   user-facing progress when it blocks a caller lemma or target theorem edge.
   Treat it as an in-turn proof work item: recursively expand callees, improve
   IR/Lean function generation, try alternate bridge propositions, run
   counterexample search, or invoke algorithm exploration for a code change.
   Return to the user only after this function guarantee is terminal
   (`verified`, `refuted`, or `unprovable_under_assumptions`) or after a
   checked external-boundary witness proves the remaining work cannot be
   advanced in the current repository/tool environment.
1. When a checked fragment is adopted, register it in the package-retained proof trace with consumed fragments, checker command, and any remaining implementation-instantiation obligations instead of hiding those boundaries in prose.
1. Normalize top-level implementation-derived theorem statements to
   `ImplementedTrace -> ProblemWitnesses -> BackendWitnesses -> Convergence`.
   `ImplementedTrace` is an assumption; `Convergence` is the lemma to prove.
1. Treat connection-level witnesses like function-level witnesses. A missing
   bridge from solver return to caller units, code fact to theorem variable, or
   backend profile to finite-precision theorem variable must be recursively
   expanded before returning. It may be reported only when a checker-backed
   minimal frontier shows that the remaining item is a code/algorithm change,
   a target input/config condition, or an generated backend coverage boundary.
1. For implementation-derived proof traces, run `python3 tools/agent_tools/check_proof_trace_alignment.py --trace-module <trace.py>` before proof expansion or verified-status claims, and fix stale source paths, StableHLO anchors, retained theorem names, and required/forbidden source-token drift first.
1. If the checker cannot be run, record `proof_status=not_run`, the exact command, and the missing environment or dependency.

## JIT-canonical IR

Use this pattern before proving implementation-derived algorithm claims.

1. Select the root from the public algorithm entrypoint consumed by the target theorem: `initialize`, `solve`, `step`, or a certificate-returning function.
1. Expand JIT root, `InitializeConfig` ownership, nested solver selection, state updates, certificate projection, and diagnostic construction into nodes and edges without importing or executing the target module.
   Expansion is saturated over JIT-lowered calls; do not tune a proof result
   by changing a recursion-depth parameter.
1. Classify nodes as mathematical state transition, linear/nonlinear solve, certificate, stopping predicate, diagnostic, performance-only helper, or implementation bookkeeping.
1. Preserve JIT-derived assignment, return, module-constant, and class-default
   facts as `generated implementation leaves`. Use these facts to cite exact equations and defaults;
   do not downgrade such facts to prose or broad `code_symbol` anchors.
1. Backward-slice the IR from the final theorem. Keep selected local obligations and assumptions that are necessary for the final claim; exclude helper structure, type facts, and convenience fields that do not affect that claim.
   Discharge instance method dispatch and constructor binding as `static_checks`
   before proof selection. Do not include dispatch edges in proof obligations;
   keep only the callee theorem or child proof scope when it is mathematically
   relevant.
   Expand visible function-pointer variants such as `self.update(...)` into
   same-module variant functions before proof selection; keep variant selection
   as a static dispatch check and the variant math as ordinary nodes.
1. For initialization and selected-scope-entry blockers, consume IR `generated implementation leaves` before
   returning. Code-derived selected-initializer equations belong in the graph
   and proof-status overlay; only the remaining non-code problem facts, such as
   selected-scope membership, regularity, differentiability, or compactness witnesses,
   may remain as mathematical assumptions.
1. Put backend arithmetic, IREE/XLA FP32, fast-math, denormal, and lowered-IR assumptions in IR `backend_trace`; treat them as theorem variables or witness obligations.
1. Assign each selected obligation to a formal theorem, existing-proof search, literature evidence, or explicit problem-class/backend assumption.

## theorem graph

Use this after JIT-canonical IR and before writing proof text.

1. Store auxiliary lemmas, assumptions, and target theorem/profile nodes as a graph.
1. Use IR `node_id`, not implementation symbol alone, as the lemma identity.
1. Connect `generated implementation leaves` as graph nodes when they are consumed by the proof
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
1. Run the theorem graph checker on the theorem graph, `proof_status.json`, and
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
   theorem graph. Prefer nodes whose proof would unlock multiple downstream
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
     existing algorithm-output projection, backend evidence, or problem-class
     witness is named.
     Immediately re-enter this same loop on that witness or next frontier.
1. A failed single-lemma route does not by itself falsify the downstream
   theorem. Keep the failed route as overlay evidence and search for a weaker
   lemma plus adjacent graph facts, code-derived identities, or problem
   witnesses whose combined certified subgraph closes the same downstream node.
   Adopt `refuted` or `unprovable_under_assumptions` for the target only when
   the checker-backed evidence rules out the target under the current theorem
   scope, not merely one proof route.
1. If a weaker proposition is verified, add a bridge edge showing what remains
   to use it in the target theorem. If a stronger route is refuted, keep the
   refutation and replace the route with a narrowed theorem or algorithm change.
1. Update the proof status table and proof note in the same pass. Every open
   row must state whether the next step is mathematical proof, implementation
   return-value projection, backend evidence binding, or theorem narrowing.
   Do not close out while a frontier row still has bare `unverified` as its
   only outcome.

## Initialize-Rooted Proof Expansion

Use this as one edge family inside the JIT-canonical IR when a runtime
module recursively initializes lower solvers, stopping predicates, or
preconditioners.

1. Record `root_initialize` and `root_config_type`, such as
   a root optimizer `initialize` with its `InitializeConfig`, or standalone
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
   proof explicitly proves a uniform bound over the selected local scope.
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
