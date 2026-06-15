# computational-optimization
<!--
@dependency-start
responsibility Documents computational optimization workflow for numerical algorithms.
upstream design ../canonical/skills.md skill canon registry
upstream design research-workflow.md research-backed change boundary
upstream design experiment-lifecycle.md experiment execution and rerun boundary
upstream design test-design.md adversarial test design boundary
downstream implementation ../../.agents/skills/computational-optimization/SKILL.md Codex discovery shim
@dependency-end
-->


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
- 実装前の edge case 設計は `$test-design` を使います。
- Python / C++ 差分 review は `$python-review` / `$cpp-review` を併用します。
- この skill は数値最適化の数学契約と検証契約を固定する責務を持ち、汎用 research workflow や実験 runner の代替ではありません。

## Optimization Contract

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

For iterative solvers, convergence evidence is a theorem about the implemented
iteration map and stopping scalar, not a runtime proof check. State the map as
`z_next = Step_impl(Problem, Config, z)` and the stopping quantity as
`R_impl(Problem, Config, z)` before changing code. If the map cannot be proved
to satisfy the target theorem under the accepted problem/config/backend
assumptions, change the algorithmic mechanism itself; do not add proof-only
`Info` fields, diagnostic gates, or extra runtime checks merely to satisfy the
proof.

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

If `agent-canon local-llm route-implementation-surface` returns
`numerical_iterative_algorithm_contract`, use this skill, the algorithm boundary
document, and the JAX loop rules as the implementation source packet before
writing code. The preferred fix is an algorithm or contract correction.
Diagnostic fields, proof `Info`, and broader numerical tests become follow-on
surfaces when the route packet makes them part of the product contract.

## Workflow

1. Classify the algorithm surface: unconstrained optimization, constrained optimization, least squares, root finding, linear solve, preconditioning, or benchmark-only.
1. Read existing algorithm docs, source dependency headers, tests, and experiment records before changing code.
1. Write the optimization contract in the run bundle or design packet before implementation.
1. Identify the first bad iteration for failures; do not diagnose only from the final NaN, Inf, or residual.
1. Create an adversarial numeric test plan before implementation: exact small case, ill-conditioned case, constraint-boundary case, non-finite guard, not-converged status, derivative check, and device / dtype case when relevant.
1. Implement the smallest responsibility-preserving change that matches the contract.
1. Validate with targeted tests and one protocol-consistent run; record skipped GPU, benchmark, or formal run evidence with reason.
1. Review numerical claims separately from code style: convergence evidence, stopping status, failure mode, tolerance rationale, and documentation alignment.

## Validation Rules

- 数値 test / experiment / benchmark を緑化するために tolerance 緩和、assertion 削除、case skip、expected 値追従、CPU alternate route をしません。
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
- numeric edge-case list in `test_plan.md`
- validation commands and result paths
- convergence / failure interpretation with observed state, first bad point, inferred cause, and unconfirmed hypotheses separated
