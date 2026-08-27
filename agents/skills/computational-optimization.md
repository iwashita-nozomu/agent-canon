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


## Reader Map

- Purpose: fix mathematical and validation contracts for numerical
  optimization, solvers, derivatives, constraints, convergence, and benchmarks.
- Section path: Purpose and Use When define scope; Boundary separates research,
  experiments, tests, and review; Optimization Contract, Workflow, Validation
  Rules, Review Route, and Outputs hold the operational rules.
- Use when: optimizer, solver, preconditioner, KKT, residual, derivative,
  tolerance, convergence, NaN/Inf, or numerical benchmark work is in scope.
- Boundary: this skill owns the optimization contract and validation contract;
  experiments, adaptive improvement, and language-specific review stay with
  their owner skills.

## Purpose

数値最適化、非線形 solver、線形 solver、preconditioner、制約条件、収束判定、gradient / Jacobian / Hessian、KKT 条件を含む変更を、数学仕様、実装責務、検証責務に分けて扱います。

## Use When

- optimizer、solver、preconditioner、line search、trust region、Newton / quasi-Newton、first-order method、stochastic optimization を変更する
- objective、constraint、residual、KKT、stopping criterion、scaling、regularization、tolerance、dtype / device behavior を診断する
- gradient / Jacobian / Hessian、finite difference、autodiff、implicit differentiation の正しさを確認する
- 数値 test、benchmark、convergence regression、NaN / Inf / divergence を扱う
- 最適化アルゴリズムの文書、実験計画、review packet を作る

## Boundary

- 外部調査や method 比較は `$research-workflow` を外側に置きます。
- 1 つの protocol の run、rerun、result artifact は `$experiment-lifecycle` と `$result-artifact-writeout` を使います。
- 実験結果を見ながら継続的に改善する場合は `$adaptive-improvement-loop` を使います。
- 実装前は semantic responsibility contract に数値検証の obligation と一次 owner を割り当てます。`$test-design` は実装 mechanism 確立後の未解決 test-owned runtime risk に限ります。
- Python / C++ 差分 review は `$python-review` / `$cpp-review` を併用します。
- この skill は数値最適化の数学契約と検証契約を固定する責務を持ち、汎用 research workflow や実験 runner の代替ではありません。

## Mathematical Intent Packet

数学または数値の挙動を修正する write-capable route は、実装者へ渡す
`mathematical_intent_packet` を先に埋めます。この packet は説明用の設計案ではなく、
数学担当者の書込範囲を決める source packet です。次のフィールドを省略せず、該当しない
場合は `not_applicable` と理由を書きます。

- `math_object`: 対象の数理オブジェクト、入力・出力、対象の主張
- `problem`: 問題設定、適用範囲、求める性質
- `variables`: 変数と固定 parameter、shape、dtype
- `domains`: 変数・parameter の domain と dimension
- `units`: 物理単位、scale、dimensionless 化
- `objective`: objective、正規化、符号規約、評価点（該当時）
- `residual`: residual、norm、符号規約、評価点（該当時）
- `constraints`: equality、inequality、box、feasibility、projection、barrier / penalty
- `equations`: 数式、境界条件、記号の対応
- `definitions`: 定義と意味（該当時）
- `assumptions`: 仮定、適用範囲、適用外条件
- `approximations`: 近似、許容範囲、誤差の扱い（該当時）
- `derivation`: 期待する導出、変形、gradient / Jacobian / Hessian の根拠
- `iteration_map`: 実装対象の反復写像、状態、受理条件、`z_next` の対応
- `update_map`: 反復ごとの更新則と実装状態の対応（反復写像と別の場合）
- `invariants`: 不変量、保存量、有限性、対称性、単調性
- `limits`: 期待する極限、漸近条件、極限の適用範囲
- `stopping_scalar`: 停止量、停止条件、tolerance、max iteration
- `failure_semantics`: infeasible、singular、non-finite、max-iter、not-converged の意味
- `equation_to_code_map`: 各 equation / definition / update と、実装の file、symbol、call path
- `math_oracle`: 最小の数学 oracle、期待値、検証可能な性質
- `counterexample`: 反例、失敗ケース、または反例が無いことの根拠
- `allowed_write_paths`: 上記 map から直接導ける定義、導出、algorithm implementation、
  numerical oracle、およびそれらを所有する docs / tests の相対 path
- `forbidden_surfaces`: math route では既定で書き込まない architecture、framework、JIT、
  compiler、backend、runtime、container、routing、environment、Docker、common infra、
  proof-tool / IR infrastructure の surface
- `separate_handoff_targets`: 明示された非数理要求、または forbidden surface の原因候補を
  別 owner へ渡す対象と理由

`allowed_write_paths` は見えているファイル一覧やエラー発生箇所から推測せず、
`equation_to_code_map` と `math_oracle` / `counterexample` から生成します。共通 infrastructure、JIT / backend、
runtime、routing、environment、Docker、証明ツールを変更しないと math oracle が閉じない場合は、
数学 writer を停止し、該当 surface の separate handoff を返します。数学 packet が無い、
または map / oracle が未接続な状態では write-capable dispatch を開始しません。

通常の run は `bootstrap_agent_run.py --math-intent-packet '<JSON>'` で packet を渡します。
bootstrap は選択された math-intent route の run manifest と spawn handoff に同じ正規化済み
packet を投影し、packet が無い場合は `math_packet_missing` で停止します。

数学 packet は数学的な依頼にだけ要求します。Docker、JIT、backend、runtime、routing、
environment、CI、container などを明示的に修正する非数理要求には適用せず、その owner route
へ渡します。両方が一つの依頼に含まれる場合は clause ごとに sibling handoff を作り、数学
writer の scope に非数理 path を混ぜません。

## Optimization Contract

The active design packet also references the run-local semantic responsibility
contract. Allocate the optimization delta's implementation action and obligations
before implementation. Assign exactly one primary verification owner to each
invariant, transition, effect, consistency, or substitutability obligation; keep
distinct supporting evidence with its distinct property or role. Numerical oracles
remain owned by the declared experiment, test, compiler, static, or proof route.

実装前の output は、optimization delta の action、semantic verification
obligations、各 obligation の一次 owner、supporting property/role、hard-edge
declaration です。`$test-design` の output は常時生成しません。owning mechanism
が確立または修復された後にも、既存 checker、static validation、design review、
既存 test、targeted validation で閉じない具体的な test-owned runtime risk が残る
場合だけ、`Activation Decision` と最小の test plan を出力します。

実装、実験、review の前に次を固定します。

1. Objective / Residual
   - 最小化する量、残差、正規化、weight、sign convention
1. Variables / Parameters
   - optimize する変数、固定 parameter、shape、dtype、device、batch semantics
1. Constraints
   - equality、inequality、box、manifold、projection、barrier / penalty、feasibility 判定
1. Derivatives
   - gradient、Jacobian、Hessian、HVP、finite-difference check、autodiff boundary
1. Algorithm State
   - iterate、step、trust radius、line-search state、preconditioner state、random seed
1. Stopping Policy
   - residual norm、objective delta、step norm、KKT residual、max iteration、failure status
1. Numerical Invariants
   - monotonicity where required、finite state、symmetry / PSD、scaling, conditioning, tolerance rationale
1. Failure Semantics
   - infeasible、singular、non-finite、max-iter、not-converged を success と分ける

### Mathematical Necessity Gate

数理的な runtime 判定、diagnostic gate、stopping check、test oracle、
proof obligation は `mathematical necessity gate` を通します。採用条件は、
public contract の precondition / invariant / postcondition、iteration map、
stopping scalar、failure semantics、accepted theorem target、または approved
design の acceptance criterion に接続できることです。接続先のない判定候補は
algorithm-change guidance、proof / review backlog、または experiment hypothesis
として記録します。

For iterative solvers, convergence evidence is a theorem about the implemented
iteration map and stopping scalar, not a runtime proof check. State the map as
`z_next = Step_impl(Problem, Config, z)` and the stopping quantity as
`R_impl(Problem, Config, z)` before changing code. If the map cannot be proved
to satisfy the target theorem under the accepted problem/config/backend
assumptions, change the algorithmic mechanism itself; do not add proof-only
`Info` fields, diagnostic gates, or extra runtime checks merely to satisfy the
proof.
Do not make the theorem pass by fixing the backend, device, compiler route,
runtime target, or dtype unless the user request, approved design, runtime
profile, public API, or config explicitly fixes that backend. Backend-specific
data is evidence for the active profile, not a replacement for the optimization
contract. Missing backend evidence is `backend_evidence_blocker`.

### Tool-Side Iterative Method Handoff

When a tool or subagent is asked to implement an iterative method, treat the
tool output as a route packet that selects an existing primitive or an explicit
local loop contract. The packet must contain:

- `iteration_map`: the concrete `Step_impl(Problem, Config, z)`.
- `stopping_scalar`: the concrete `R_impl(Problem, Config, z)`.
- `state_tuple`: all loop-carried state, with owner and dtype / device boundary.
- `reuse_surface`: existing solver, library, framework primitive, or repo helper
  selected as the first implementation surface.
- `failure_semantics`: max-iteration, breakdown, singular, non-finite,
  infeasible, and nonconvergence statuses.
- `validation_surface`: static checker, smallest deterministic numerical case,
  and any experiment or benchmark path kept separate from correctness evidence.

If deterministic responsibility search routes the task to
`numerical_iterative_algorithm_contract`, use this skill, the algorithm boundary
document, and the JAX loop rules as the implementation source packet before
writing code. The preferred fix is an algorithm or contract correction.
Diagnostic fields, proof `Info`, and broader numerical tests become follow-on
surfaces when the route packet makes them part of the product contract.

## Workflow

1. Classify the algorithm surface: unconstrained optimization, constrained optimization, least squares, root finding, linear solve, preconditioning, or benchmark-only.
1. Read existing algorithm docs, source dependency headers, tests, and experiment records before changing code.
1. Write the optimization contract in the run bundle or design packet before implementation.
1. Identify the implemented recurrence, state transition, stopping scalar,
   acceptance rule, and failure semantics that the contract requires.
1. Identify the first bad iteration or first contract-violating code-side
   mechanism for failures; final NaN, Inf, residual, or failing assertion is
   only symptom evidence.
1. Select the algorithmic repair route before editing tests: initializer,
   update rule, line search, inner-solver policy, regularization, feasibility
   restoration, scaling, or status semantics.
1. Create the targeted numeric validation plan after the contract and repair
   route are fixed: exact small case, ill-conditioned case,
   constraint-boundary case, non-finite guard, not-converged status, derivative
   check, and device / dtype case when relevant.
1. Implement the responsibility-preserving change that matches the contract and
   validation plan.
1. Validate with targeted tests and one protocol-consistent GPU run; record
   skipped GPU, benchmark, or formal run evidence as a blocker with reason
   instead of replacing it with CPU computation.
1. Review numerical claims separately from code style: convergence evidence, stopping status, failure mode, tolerance rationale, and documentation alignment.

## Validation Rules

- 数値 test / experiment / benchmark を緑化するために tolerance 緩和、assertion 削除、case skip、expected 値追従、CPU alternate route、CPU smoke、CPU-only regression をしません。
- solver、optimizer、JAX / XLA / IREE lowering、convergence、residual、benchmark、experiment validation などの計算テストは CPU で実行しません。GPU が使えない場合は `gpu_validation_blocker=<reason>` と evidence を残します。
- `converged=false`、`max_iter`、non-finite intermediate、constraint violation は pass evidence ではありません。
- runtime proof-only fields or diagnostic gates are not convergence evidence;
  use them only when they are genuine execution outputs needed by the user-facing
  algorithm contract.
- Final value だけでなく、first bad iteration、finite state、residual components、reference norm、tolerance、status flag を確認します。
- Constraint つき問題では objective だけでなく feasibility と KKT / complementarity を分けます。
- Linear solver / preconditioner では residual norm、reference norm、preconditioner summary、breakdown status を分けます。
- Randomized or stochastic optimization では seed、sample budget、variance / confidence、rerun policy を保存します。
- Performance claim は correctness evidence と分け、同じ run を両方の根拠にしません。

## Review Route

- Mathematical or scientific-computing risk: `scientific_computing_reviewer`
- Benchmark or performance claim: `benchmark_reviewer` plus `reproducibility_reviewer`
- Python implementation: `$python-review`
- C / C++ implementation: `$cpp-review`
- Paper or report claim: `$report-writing` with the relevant research reviewer

## Outputs

- `optimization_contract.md` or an equivalent section in `design_brief.md`
- pre-implementation semantic responsibility allocation with action, obligations,
  primary owners, and hard-edge declarations
- numeric edge-case list in `test_plan.md` only when post-mechanism unresolved
  test-owned runtime risk activates `$test-design`
- validation commands and result paths
- convergence / failure interpretation with observed state, first bad point, inferred cause, and unconfirmed hypotheses separated

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/computational-optimization.md`.
1. Use this skill for optimizer, solver, preconditioner, residual, KKT, convergence, derivative, tolerance, or numerical benchmark work.
1. Before implementation or experiment runs, fix an optimization contract: objective or residual, variables, constraints, derivatives, algorithm state, stopping policy, numerical invariants, and failure semantics.
1. Route mathematical runtime checks, diagnostic gates, stopping checks, test
   oracles, and proof obligations through the `mathematical necessity gate`:
   connect each one to the public contract, iteration map, stopping scalar,
   failure semantics, accepted theorem target, or approved design acceptance
   criterion before adding it to implementation or validation evidence.
1. For iterative solvers, treat convergence evidence as a theorem about the
   implemented iteration map and stopping scalar, e.g.
   `z_next = Step_impl(Problem, Config, z)` and
   `R_impl(Problem, Config, z)`. If this map cannot satisfy the target theorem
   under the accepted problem/config/backend assumptions, change the algorithmic
   mechanism itself. Do not add proof-only `Info` fields, diagnostic gates, or
   extra runtime checks merely to satisfy the proof.
1. When tool-side routing returns `numerical_iterative_algorithm_contract`, build
   an explicit route packet before code changes: `iteration_map`,
   `stopping_scalar`, `state_tuple`, `reuse_surface`, `failure_semantics`, and
   `validation_surface`. Prefer existing solver/library/framework primitives or
   repo helpers as the first implementation surface, and keep correctness
   validation separate from experiment or benchmark evidence.
1. For algorithm fixes, enter through the optimization contract and implemented
   mechanism before changing tests. Record the public entrypoint, recurrence or
   state transition, invariant, stopping or acceptance scalar, and failure
   semantics; then select the code-side repair route. Existing tests are
   symptom and placement evidence, while expected values, tolerances, and new
   oracle cases are updated after the algorithm route is fixed.
1. Do not make the theorem pass by fixing the backend, device, compiler route,
   runtime target, or dtype unless the user request, approved design, runtime
   profile, public API, or config explicitly fixes that backend. Backend-specific
   data is evidence for the active profile, not a replacement for the
   optimization contract. Missing backend evidence is
   `backend_evidence_blocker`.
1. For JAX/XLA/IREE iterative solvers, keep lowering-friendly loop structure in
   the implementation: do not feed residual / convergence / breakdown status
   produced inside `lax.while_loop` back into the next `cond`, and normalize
   Python scalar settings to dtype-specific JAX arrays at the JIT boundary. Use
   `documents/conventions/python/15_jax_rules.md` as the detailed code-writing
   rule.
1. If the task includes external method comparison or claims, also use `$research-workflow`; if it includes a concrete run protocol or rerun decision, also use `$experiment-lifecycle`.
1. If the owning mechanism is established or repaired and a concrete
   test-owned runtime risk remains outside existing validation, activate
   `$test-design` and emit its `Activation Decision`; otherwise keep the
   pre-implementation obligation allocation as the test-design output and do
   not emit a test plan. When activated, include exact small cases,
   ill-conditioned cases, constraint-boundary cases, derivative checks,
   non-finite guards, and not-converged status handling only when relevant.
1. Do not green numerical tests by relaxing tolerances, deleting assertions,
   skipping cases, changing expected values to match current output, or running
   computational tests on CPU; using CPU as substitute evidence is a validation
   blocker, not pass evidence. Solver, optimizer, JAX/XLA/IREE lowering,
   convergence, residual, benchmark, and experiment validation must run on the
   GPU target or be recorded as `gpu_validation_blocker=<reason>`.
1. Diagnose failed runs by first bad iteration, finite state before failure, residual components, reference norm, tolerance, status flag, and unconfirmed hypotheses; do not infer cause only from the final NaN, Inf, or residual.
1. Keep correctness evidence separate from performance evidence; benchmark claims need reproducibility and confounder review.
1. Route review by risk: `scientific_computing_reviewer` for math/numerical risk, `benchmark_reviewer` for performance claims, `$python-review` or `$cpp-review` for implementation diffs, and `$report-writing` for reader-facing claims.
