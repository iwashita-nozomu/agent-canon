# algorithm-proof-exploration

<!--
@dependency-start
responsibility Documents theorem-driven algorithm exploration before final formal proof adoption.
upstream design formal-proof-workflow.md checker-backed formal proof workflow.
upstream design computational-optimization.md numerical optimization contract workflow.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds Algorithm Expansion IR.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py builds lemma dependency graphs.
upstream implementation ../../tools/agent_tools/proof_path_analyzer.py validates proof-status overlays.
upstream implementation ../../tools/agent_tools/algorithm_flowchart.py renders implementation/proof-state Mermaid diagrams.
upstream implementation ../../tools/agent_tools/ir_graph_correspondence.py checks IR equation facts against lemma graphs.
upstream implementation ../../rust/agent-canon/src/algorithm_ir_to_lean.rs lowers IR facts into Lean route artifacts.
upstream implementation ../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections from IR facts.
upstream design ../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop capabilities by frontier shape.
downstream implementation ../../.agents/skills/algorithm-proof-exploration/SKILL.md exposes the skill to Codex.
@dependency-end
-->

## Purpose

`algorithm-proof-exploration` は、証明義務を入力にしてアルゴリズムを探索・修正する
workflow です。対象は optimizer、solver、preconditioner、KKT 系、有限精度経路、
certificate-returning algorithm などです。

この skill は、実装から Algorithm Expansion IR と Lemma Dependency Graph を作り、
target theorem に対してどの実装自由度、problem-class witness、runtime certificate、
algorithm change が有効かを探索します。証明 route の採用、checker 実行、
counterexample / unprovable-under-assumptions claim の最終判定は
`$formal-proof-workflow` に渡します。

## Use When

- アルゴリズムの収束性、停止性、certificate soundness、有限精度誤差、solver-chain
  handoff に対して、どのアルゴリズム構造なら証明義務を満たせるか探索したい
- 実装を証明可能な形に直すための algorithm choice / runtime certificate /
  problem-class witness を見つけたい
- `Algorithm Expansion IR`、`Lemma Dependency Graph`、proof status overlay、
  algorithm blocker frontier を作る・更新する
- formal proof 側で閉じない場合に、どのアルゴリズム変更が必要かを整理したい

## Relationship To `$formal-proof-workflow`

- この skill は「アルゴリズム探索」を担当します。
  - root algorithm の機械展開
  - target theorem ごとの lemma graph/profile 作成
  - algorithmic blocker と実装自由度の分類
  - algorithm-change guidance と formal-proof handoff の記録
- `$formal-proof-workflow` は「証明探索と採用」を担当します。
  - theorem statement の形式化
  - Lean/Isabelle/Coq/SMT での checker 実行
  - 単独補題 route、弱い補題束、certified subgraph の探索
  - verified/refuted/unprovable-under-assumptions claim の採用
  - reader-facing proof note の証明状態表

両者は必ず接続します。アルゴリズム由来の証明 task では、この skill がアルゴリズム候補と
実装変更候補を作り、それを `$formal-proof-workflow` が checker-backed に評価します。

## Completion Condition

この skill の終了条件は、目的の定理そのものについて次のいずれかを
checker-backed に採用できることです。

- 目的の定理が証明された。
- 現在の仮定と実装経路からは目的の定理を導けない、つまり仮定不足であることが
  証明された。
- terminal outcome は `verified`、`refuted`、または
  `unprovable_under_assumptions` のいずれかです。
  `unverified_with_next_witness` は次に形式証明へ戻す witness queue です。

algorithm blocker の分類、algorithm-change guidance、IR/graph の接続確認、
formal-proof handoff の明確化は中間成果です。これらだけでは終了しません。
アルゴリズム変更が必要な場合も、その変更案を出しただけでは終了せず、現在の仮定不足を
証明するか、変更後のアルゴリズムで目的の定理を証明するところまで進めます。
`unverified_with_next_witness` は formal-proof 側へ戻す探索 queue であり、
アルゴリズム探索の完了ではありません。証明 path が閉じない場合は、
current IR / assumption ledger から導けないことを checker-backed に示してから、
最小の algorithm change、problem-class witness、または external boundary として
採用します。

## Canonical Flow

1. Target theorem:
   - local convergence
   - certificate soundness
   - finite-precision floor
   - solver-chain reachability
   - infeasibility / unboundedness certificate
   - problem-class narrowing
1. Root algorithm:
   - public `initialize`
   - public `solve`
   - one-step transition `step`
   - certificate-returning function
1. Operational algorithm assumption:
   - implementation-derived theorem では、抽出した root algorithm を
     `trace follows A_impl / Step_impl` という operational assumption として
     置く
   - convergence、certificate soundness、finite termination、residual
     reachability は、この operational assumption から導く lemma / theorem であり、
     assumption にしてはいけない
   - proof status overlay には `operational_assumptions` として記録し、
     `open_frontier` や `external_assumptions` と混ぜない
1. Algorithm Expansion IR:
   - use `python3 tools/agent_tools/algorithm_expansion_ir.py --python-symbol <path.py::qualname> --target-theorem <target>`
   - expansion saturates over AST-resolved calls
   - do not add recursion-depth knobs to change proof conclusions
   - keep instance dispatch and constructor binding as static checks unless they are mathematical facts
1. Lemma Dependency Graph:
   - use `python3 tools/agent_tools/algorithm_lemma_graph.py --target-profile <profile>`
   - keep multiple profiles for one algorithm when needed
   - use graph nodes and edges for auxiliary lemmas, bridge lemmas, assumptions, failed routes, and adoption decisions
   - treat generated lemma groups as products of the Algorithm Expansion IR.
     If the algorithm changes, reset generated lemma groups and proof-status
     adoption for those IR-backed nodes by regenerating IR, regenerating graphs,
     and rebuilding the overlay. Do not carry old generated lemmas across an
     algorithm change by editing labels or prose.
   - generate checker-facing Lean route artifacts with
     `tools/bin/agent-canon algorithm-ir-to-lean`; do not introduce a
     hand-written algorithm-specific operation abstraction as a new proof
     entrypoint when current IR `expression_ast` and `control_facts` can supply the
     implementation evaluation order. Structure access must be handled by the
     post-IR Rust projection pass, not by algorithm-specific generated shapes.
1. Algorithm Flowchart:
   - use `python3 tools/agent_tools/algorithm_flowchart.py` after IR and
     LemmaGraph generation when a human or agent needs to see the implemented
     iteration path and proof-state overlay at once
   - render from IR / LemmaGraph / `proof_status.json`, not from a hand-drawn
     diagram
   - use `--view runtime` or `--view core --include-code-facts` when the
     artifact must show implementation flow without proof-only branches or
     labels
   - treat the Mermaid chart as navigation evidence only. It may show where a
     block is verified, open, or external, but proof completion still comes from
     `$formal-proof-workflow` checker evidence and `proof_path_analyzer.py`
1. Equation projection:
   - after LemmaGraph generation, use
     `python3 tools/agent_tools/ir_graph_correspondence.py` for theorem-critical
     assignment and return equations
   - check iteration slices by `source_symbol` and `equation_tags`, for example
     `step_update`, `reduced_kkt`, `minres_defaults`, and initialization tags
   - if an equation fact is absent from the graph or lacks a
     `lemma_consumes_code_fact` edge, fix IR extraction or graph generation
     before writing proof prose or Lean bridge lemmas
   - for reduced block-system / KKT / iterative-solver-chain equations, use
     `python3 tools/agent_tools/kkt_equation_section.py` or the relevant
     equation-section generator with the current Algorithm Expansion IR files
   - if the generator fails because a required code fact is missing, classify
     the gap as IR extraction weakness or code-shape opacity before writing
     proof prose
   - displayed implementation formulas in that section are substituted from
     matched IR `code_facts[*].expression`; proof notes should link to the
     generated section instead of carrying parallel hand-written runtime
     equations
   - theorem-critical IR equations must be hand-translated into candidate typed
     mathematical Lean propositions. IR extraction tells which equations are
     present; this skill explores which bridge proposition is useful for the
     target theorem. Do not freeze on one bridge shape. Generate multiple
     bridge candidates at the abstraction level required by the target theorem,
     check or refute them when possible, and classify each candidate before
     choosing the next route. Do not leave theorem-critical returned values
     unconstrained when the current IR contains equations that determine or
     bound them.
   - candidate selection is recursive and target-driven. State the current
     target proposition `P`, run checker/tactic search such as `aesop?`,
     inspect unsolved subgoals or missing hypotheses, translate those gaps into
     bridge candidates, check whether current Lean functions / generated IR
     facts prove or refute each candidate, and rerun the proof of `P`. Repeat
     until `P` is proved, refuted, shown unprovable under the current top-level
     assumptions, or reduced to a strictly smaller named witness. A flat
     candidate list is only input to this loop.
1. Algorithm frontier extraction:
   - choose graph frontier nodes by their algorithmic impact, not prose order
   - normalize each target-facing blocker to implementation identity,
     certificate plumbing, reachability/existence mechanism, algorithmic choice,
     external assumption binding, or problem-class witness
   - do not treat a failed single-lemma route as an algorithm failure. Hand
     proof-route alternatives to `$formal-proof-workflow`; this skill uses the
     returned proof outcome to decide whether an algorithm change is needed
  - when formal-proof returns a missing witness or assumption-insufficiency
    result, decide whether that gap is better solved by changing the algorithm,
    adding a runtime certificate, narrowing the problem class, or leaving an
    external assumption boundary
  - frontier を、対象アルゴリズム入力と無関係な仮定注入で閉じてはいけません。
    固定された algorithm では、数学的仮定は theorem top level の
    `Problem` と config object にだけ置きます。途中で必要になる主張は仮定ではなく
    `top_level_problem_config_lemma` のような problem/config-derived lemma として持ち、
    その top-level 仮定と抽出済み code path から証明します。
    implementation trace や backend/runtime semantics のような architecture
    assumption は許可しますが、Problem/config assumption とは別ラベルにします。
  - ほしい局所仮定は premise ではなく導出 target として扱います。各中間条件に
    candidate lemma 名を付け、すべての変数を `Problem`、config、IR が抽出した
    path state、code fact、または許可された architecture boundary のどれかへ
    束縛してから、`$formal-proof-workflow` へ渡して top-level 仮定と code path
    から導けるかを試します。失敗した場合は、theorem を緩める前に lemma 形状を変えます:
    quotient / projection、上界補題、selected-scope certificate、finite-prefix
    certificate、same-units conversion、algorithm に有用な returned-runtime
    certificate を試します。ほしい条件を独立仮定に昇格してはいけません。どの導出 route も
    閉じない場合だけ、最小 blocker を top-level Problem/config property の不足、
    external architecture evidence の不足、または変更すべき algorithmic choice として返します。
  - if formal-proof returns only `unverified_with_next_witness`, feed that
    named witness back to formal-proof before classifying an algorithmic
     blocker; do not turn a proof-search queue item into algorithm-change
     guidance
  - if the returned witness is a function-level guarantee whose absence blocks
    a caller lemma or target theorem edge, continue the recursion in the same
    turn. Do not return it to the user as "still unconnected" unless no
    repository/code/tool action can advance it and that external boundary is
    itself checker-backed or explicitly unavailable
  - current algorithmic choice を blocker と分類する前に、target theorem に効く
    algorithm block をすべて `$formal-proof-workflow` 側で命題化させます。
    initializer、stopping scalar、step length / acceptance selection、
    direction construction、nested solver certificate、state update、
    residual / merit recomputation、final scalar binding の返却値が theorem に影響するなら、
    route call や unconstrained theorem variable のまま blocker にしてはいけません。
    その場合は、より小さい formal-proof witness として戻します。algorithmic blocker として
    返せるのは、残る穴が missing contraction、missing residual-merit selection、
    missing problem-class bound、missing backend boundary、checker-backed refutation などの
    semantic mechanism まで縮約された場合だけです。
1. Algorithmic blocker exploration:
   - when a target-facing blocker remains after formal-proof exploration,
     classify whether it comes from missing problem assumptions, missing
     external evidence, or a current algorithmic choice
   - function-level blockers must be reported as a causal chain, not as a flat
     list of missing lemmas.  For each recursive function on the target path,
     state:
     `function`, `unguaranteed property`, `why that output can be wrong or
     insufficient`, `which caller-side lemma becomes unprovable`, and
     `which target theorem edge fails`.  Example shape:
     `minres._run_minres_solve cannot guarantee requested physical residual for
     the current preconditioned KKT operator -> kkt._solve cannot bound
     direction error -> pdipm._pdipm_step cannot prove outer residual decrease
     -> finite localOptimal reachability remains unproved`.
     If a function calls another function, recursively expand the callee until
     the gap is a problem/config witness, backend semantics boundary, or
     algorithmic choice.  Do not stop at "solver precision unverified" when a
     caller-visible output and failed downstream lemma can be named.
     A callee name is never itself the algorithmic blocker. Before reporting an
     algorithmic blocker, expand the callee's generated equations into the
     smallest relevant function predicates: input/output relation, return
     binding, loop-exit reason, stopping predicate, breakdown / exception
     predicate, and nested solver / callback output relation. Only after those
     predicates are verified, refuted, proved unprovable under the current
     top-level assumptions, or reduced to an external backend boundary may the
     blocker be returned.
   - distinguish `guarantee_unconnected` from `guarantee_refuted`.
     `guarantee_unconnected` means the current IR / Lean function path has not
     yet proved the property and must be re-entered as a work queue.
     `guarantee_refuted` means a checker-backed theorem, counterexample,
     model, or implementation trace shows the property is false under the
     current top-level assumptions and code path.  Do not report "this
     function cannot guarantee X" as a terminal blocker unless the refutation
     is checked.  If a function guarantee is refuted, record the exact
     refutation theorem or model and prove the propagation:
     function output guarantee fails, therefore the caller-side lemma cannot
     be established, therefore the target theorem edge is false or
     unprovable under the current assumptions.
   - do not return user-facing progress with a function guarantee still marked
     `guarantee_unconnected` when that unconnected guarantee is the reason a
     caller-side lemma or target theorem edge is open.  Re-enter the recursive
     function frontier immediately: generate the next callee/function property,
     prove it, refute it, prove it unprovable under the current top-level
     assumptions, or change the algorithm and regenerate IR/graphs.  A smaller
     named witness is not a user-facing stopping point for this class of gap;
     it is the next in-turn work item.
   - for initialization, basin-entry, or selected-scope-entry blockers, first normalize
     the implementation as a selected initializer
     `z_init = Init(Problem, InitializeConfig)`. Do not treat a hard-coded zero,
     default vector, supplied state, or previous-state reuse as a mathematical
     theorem premise unless the algorithm genuinely requires that value. If the
     current selected initializer is too weak, classify the gap as either a
     problem-class witness for that initializer or an algorithmic choice to add
     a stronger initializer / Phase I / globalization path.
   - after changing initialization logic, regenerate IR/graphs and require
     `$formal-proof-workflow` to consume the newly extracted initialization
     code facts before returning to the user. Code-visible initial point,
     epigraph, slack/multiplier floor, initial residual, and child-state facts
     are not acceptable user-facing blockers
   - if it is algorithmic, enumerate the smallest implementation degrees of
     freedom that could make the theorem provable and translate each candidate
     into a proof obligation before editing code
   - after any algorithm change, regenerate IR/graphs and re-enter the same
     algorithm frontier; do not stop at "this change should help" when the
     target theorem can still be tested by `$formal-proof-workflow`
   - keep the implemented trace as the operational assumption. New bounds or
     certificates must be derived from the extracted code path and theorem
     witnesses, not from proof-only production fields
1. Algorithm change guidance:
   - expose a runtime certificate
   - return same-run true residuals
   - remove unsound gates
   - change an algorithmic choice only when the proof obligation shows that the
     current choice blocks the theorem
   - replace hard-coded initial points with a proof-visible selected initializer
     when the target theorem needs basin/selected-scope entry, and state whether the
     remaining proof obligation is on `Init(Problem, InitializeConfig)` or on a
     stronger Phase-I/globalization algorithm
   - add Phase I / globalization when the theorem needs basin entry
   - narrow a theorem to selected local scope / warm-start assumptions
   - add problem-class or backend evidence witnesses
1. Formal proof handoff:
   - pass exact theorem variables, proof artifacts, checked fragments, and remaining obligations to `$formal-proof-workflow`
   - do not mark a graph path verified unless checker-backed proof nodes cover the target chain

## Artifact Contract

Use these names in run bundles, proof notes, or `lean/<proof-theme>/` artifacts:

- `proof_algorithm_ir`: source root, target theorem, code facts, static checks.
- `proof_lemma_graph`: target chains and dependency edges.
- `proof_operational_assumptions`: extracted implemented-algorithm trace
  premise, such as `trace follows A_impl / Step_impl`.
- `proof_algorithm_flowchart`: Mermaid or Markdown diagram generated from the
  current IR, LemmaGraph, and proof-status overlay.
- `algorithm_frontier`: current algorithmic blockers, candidate changes, and
  handoff targets.
- `algorithm_change_guidance`: implementation changes needed for provability.
- `formal_proof_handoff`: exact claims and checker commands for `$formal-proof-workflow`.

## Guardrails

- Do not prove Pyright/type facts unless they are mathematical dependencies of the target theorem.
- Do not add proof-only production config or state.
- Do not treat IR or graph reachability as proof completion.
- Do not treat convergence as an assumption. The implemented algorithm trace is
  the assumption; convergence is the lemma derived from that trace plus
  problem/backend witnesses.
- Do not treat one failed formal-proof route as an algorithmic blocker until
  `$formal-proof-workflow` has checked whether a weaker or bundled route can
  close the target.
- Do not split one proof theme across competing proof notes. Implementation path explanation may live in Design docs; mathematical proof text belongs in `notes/themes/`.
