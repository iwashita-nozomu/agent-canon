<!--
@dependency-start
contract reference
responsibility Summarizes Lean/Mathlib/Aesop/Plausible/LeanSearch capabilities for AgentCanon proof workflows.
upstream design README.md lists proof-tool documentation entrypoints.
upstream implementation ../../tools/agent_tools/lean_proof_env.py creates Lean proof-search, theorem-search, and counterexample environments.
upstream design ../../agents/skills/formal-proof-workflow.md routes checker-backed proof attempts.
upstream design ../../agents/skills/algorithm-proof-exploration.md routes algorithm-derived proof frontiers.
upstream design ../../references/agent-canon-technology-bibliography.md records adopted Lean sources.
downstream design ../../.agents/skills/formal-proof-workflow/SKILL.md exposes the runtime Lean proof route.
@dependency-end
-->

# Lean Capability Matrix

This note is the AgentCanon routing guide for Lean-backed proof work.  It
answers a practical question: given a frontier node from an Algorithm Expansion
IR / Lemma Dependency Graph, which Lean feature should be tried before the
agent changes the algorithm, weakens the theorem, or returns a blocker?

The matrix is evidence for workflow design, not proof authority.  A claim is
verified only when the target Lean file checks without `sorry`, unchecked
axioms, or an equivalent proof escape hatch.

## Reader Map

Use this matrix to answer which Lean, Mathlib, Aesop, Plausible, search, and
machine-interface features should be tried for a proof frontier before changing
an algorithm or returning a blocker. Start with Source Sweep and Capability
Table, then read Default Lean Attempt Order and Environment Policy for routing.
Optimization/Solver Mapping and Cleanup Rule cover specialized frontiers and
retirement of temporary proof paths.

## Source Sweep

Primary and near-primary sources used for this matrix:

| Source | URL | Used For |
| --- | --- | --- |
| Lean Language Reference | <https://lean-lang.org/doc/reference/latest/> | Kernel, tactic reference, simplifier, `grind`, Lake, library-search tactic behavior. |
| Theorem Proving in Lean 4 | <https://lean-lang.org/theorem_proving_in_lean4/> | Basic theorem-proving workflow, tactics, propositions, induction, structures, type classes. |
| Mathlib documentation | <https://leanprover-community.github.io/mathlib4_docs/Mathlib> | Mathlib module and tactic surface. |
| Searching for Theorems in Mathlib | <https://leanprover-community.github.io/blog/posts/searching-for-theorems-in-mathlib/> | Search workflow and limitations for Mathlib theorem discovery. |
| Aesop documentation | <https://leanprover-community.github.io/mathlib4_docs/Aesop/Frontend/Tactic.html> | `aesop` / `aesop?` behavior and generated proof suggestion route. |
| Aesop repository | <https://github.com/leanprover-community/aesop> | Aesop as white-box proof search for Lean 4. |
| Plausible repository | <https://github.com/leanprover-community/plausible> | Property-based counterexample search integrated with Lean tactics and `#eval` checks. |
| Loogle | <https://loogle.lean-lang.org/> | Type/signature and pattern search over Lean/Mathlib definitions and theorems. |
| LeanSearch | <https://leansearch.net/> | Natural-language theorem search over Mathlib4, with privacy caveat. |
| LeanSearchClient repository | <https://github.com/leanprover-community/LeanSearchClient> | Lean-side command syntax for LeanSearch, LeanStateSearch, and Loogle services. |
| Pantograph repository | <https://github.com/leanprover/Pantograph> | Machine-to-machine Lean 4 interface candidate for proof-search agents. |
| Lean REPL repository | <https://github.com/leanprover-community/repl> | JSON stdin/stdout REPL candidate for lightweight Lean agent harnesses. |
| LeanDojo repository | <https://github.com/lean-dojo/LeanDojo> | Programmatic Lean interaction and theorem-proving benchmark lineage; original package is deprecated in favor of newer LeanDojo work. |

## Capability Table

| Frontier Shape | Lean Feature | Use First When | Algorithm-Proof Use | Boundary |
| --- | --- | --- | --- | --- |
| Definitional equality, direct code equation | `rfl`, `rw`, `simp`, `simpa`, `simp only`, `simp_all` | IR code facts already expose the expression, and the proof just needs substitution/normalization. | Step updates, residual bindings, linear-solver reconstruction equations. | Do not hand-copy formulas; use IR-generated equation facts and then simplify. |
| Direct theorem or local hypothesis closes goal | `exact`, `apply`, `assumption`, `have`, `suffices`, `calc` | The target theorem is already in context or one library lemma away. | Bridge lemmas that compose checked fragments. | `exact?` / `apply?` may suggest candidates, but suggestions must be copied into a checked proof. |
| Propositional structure, records, constructors | `constructor`, `cases`, `rcases`, `obtain`, `use`, `aesop`, `aesop?` | The goal is packaging, conjunction/disjunction, existential witness, structure field extraction, or relation composition. | Solver-chain certificate packaging, proof-status minimality, path-indexed handoffs. | Aesop is a search tactic, not a certificate by itself; retain the checked proof text or checker log. |
| Nat/Int linear arithmetic | `omega`, `grind` | The goal is over `Nat`/`Int`, floors, monotone counters, bounded iteration indices, or finite-hit statements. | Floor preservation, finite-prefix counters, proof-status minimality over graph depths. | `omega` is specialized; `grind` may do more but can explode on large branchy encodings. |
| Ordered ring/field linear inequalities | Mathlib `linarith` | The goal is linear arithmetic over ordered rings/fields after normalization. | Budget inequalities once encoded over `Real` or an ordered semiring with appropriate hypotheses. | Needs Mathlib environment and suitable algebraic hypotheses. |
| Polynomial/nonlinear arithmetic | Mathlib `nlinarith`, `ring`, `ring_nf`, `norm_num` | Multiplicative constants, squared quantities, or polynomial recurrence bounds appear. | Local recurrence inequalities of the form `R_next <= c * R^2 + ...`; algebraic normalization before `linarith`/`nlinarith`. | Does not solve analytic estimates or missing Lipschitz/Taylor assumptions. |
| Positivity and monotonicity | Mathlib `positivity`, `gcongr`, monotonicity lemmas | A proof needs nonnegativity, order-preserving maps, or bound propagation through expressions. | Floor bounds, norm bounds, damping factors, safe denominators. | Requires the positivity/monotonicity premise to be expressible; it cannot invent problem-class facts. |
| Broad first-order / SMT-style search | Lean `grind` | Constructors, equalities, inequalities, case splits, and small algebraic facts are mixed. | Retrying compact frontier lemmas before declaring an algorithmic blocker. | Use on focused obligations; avoid feeding a whole generated graph into one `grind` goal. |
| Theorem discovery | `exact?`, `apply?`, `rw?`, `simp?`, Loogle, LeanSearch, Mathlib docs | A statement looks standard or library-backed. | Search for norm/order/algebra/topology lemmas before creating local stubs. | Search is heuristic; absence of a result is not unprovability. |
| Counterexample search for over-strong claims | Plausible `plausible`, `Plausible.Testable.check` | The proposition is executable over sampled finite data, or a local encoding can produce sampled witnesses. | Refute too-strong bridge candidates before treating them as algorithm blockers. | A Plausible counterexample refutes the encoded executable claim, not every analytic real-valued theorem. |
| Agent theorem-search interface | LeanSearchClient import surface, LeanSearch/Loogle service commands | An agent needs a Lean-side theorem-search entrypoint or a service-backed search query. | Retrieve candidate lemmas for focused frontier nodes before writing local stubs. | Service calls are heuristic and may be unavailable; final proof still requires kernel/lake checking. |
| Machine-to-machine proof interaction | Pantograph, Lean REPL, LeanDojo-style harnesses | The task needs tactic execution state, proof search, benchmark data, or a persistent agent harness. | Future proof-search backend for generated frontier nodes. | Treat as optional backend infrastructure; do not make normal local proof checks depend on heavyweight services. |
| Environment and dependencies | Lake, `lean-toolchain`, `lean_proof_env.py` | A proof needs Mathlib/Aesop/Plausible/LeanSearchClient or a stable checked environment. | Pin dependencies once for an active proof package; use the reusable proof env for probes and fallback checks. | Do not spend every proof retry rediscovering the same environment boundary. |

## Default Lean Attempt Order

For each selected frontier node:

1. Bind the theorem statement to IR code facts or an explicit top-level
   `Problem + Config + ImplementedTrace` assumption.
1. Try direct proof normalization: `rfl`, `rw`, `simp only`, `simp`, `simpa`,
   `exact`, `apply`.
1. Try structural automation: `constructor`, `cases`/`rcases`, `obtain`,
   `use`, then `aesop?` / `aesop`.
1. Classify arithmetic:
   - `Nat` / `Int`: try `omega`, then focused `grind`.
   - ordered linear arithmetic: normalize with `simp` / `ring_nf`, then
     `linarith`.
   - polynomial inequalities: normalize with `ring` / `ring_nf` / `norm_num`,
     then `nlinarith`.
   - positivity or monotonicity: try `positivity`, `gcongr`, and relevant
     Mathlib order lemmas.
1. Search existing facts: `exact?`, `apply?`, `rw?`, `simp?`, Loogle,
   LeanSearch, and Mathlib docs.  Adopt only checked suggestions.
1. Before treating a strong candidate as a blocker, try an executable
   Plausible counterexample probe when the claim can be sampled without
   changing the theorem's meaning.
1. If the frontier remains open, decide whether the failure is an
   implementation/code-fact gap, a missing top-level problem/config property, a
   backend axiom boundary, or an algorithmic blocker.

## Environment Policy

AgentCanon owns a reusable proof environment for Mathlib, Aesop, Plausible, and
LeanSearchClient:

```bash
python3 tools/agent_tools/lean_proof_env.py smoke \
  --env-dir reports/formal-proof/lean-proof-env \
  --execute
```

Use `all-smoke` when proving environment readiness for agents:

```bash
python3 tools/agent_tools/lean_proof_env.py all-smoke \
  --env-dir reports/formal-proof/lean-proof-env \
  --execute
```

Use it before saying that Mathlib, Aesop, Plausible, or LeanSearchClient is unavailable.  Generated
environment files live under `reports/formal-proof/` and are local artifacts,
not source.  The source tree should not commit that generated Lake package.

For an active repository proof theme, prefer paying the environment cost once:
pin Lean and Mathlib/Aesop/Plausible/LeanSearchClient in the topic-local Lake
package, keep `.lake/` ignored, and make ordinary proof attempts run through `lake build`.  Use the
reusable proof env for exploratory checks, cross-theme probes, and fallback
validation, not as a reason to revisit dependency setup every time.

## Optimization And Solver Mapping

For optimization and nested-solver convergence themes:

- Code equations from public solve/step/update functions and nested linear or
  nonlinear solver paths are IR facts first.  Lean should consume those facts
  through generated equation sections and correspondence checks.
- Solver-chain packaging, path-indexed certificates, and proof-status
  minimality are structural and should use `constructor`, `cases`, `exact`,
  `apply`, and `aesop` before hand-written proof plumbing.
- Floor and finite-prefix claims should use `omega` or `grind` when expressed
  over `Nat`/`Int`.
- Local decrease/recurrence is usually the first genuinely analytic frontier.
  Lean can
  check the algebraic shell with `ring_nf`, `linarith`, `nlinarith`, and
  monotonicity/positivity tactics after the problem-class lemmas provide the
  Taylor/Lipschitz/model bounds.  Lean cannot synthesize those analytic
  problem-class assumptions from implementation code alone.
- Backend FP32/IREE semantics remain external axioms unless the task is
  specifically to formalize the backend.

## Cleanup Rule

Delete or retire proof paths that:

- duplicate IR-generated equations in prose,
- keep old implementation symbols after IR regeneration,
- require assumptions not grounded in `Problem`, config, implemented trace,
  backend profile, or a formal-library theorem,
- are only weaker restatements of a more precise Lean-checked fragment.

Do not delete a path solely because it is hard; first classify it as verified,
refuted, unprovable under current assumptions, or replaced by a strictly
smaller named frontier.
