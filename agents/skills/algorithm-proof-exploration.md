# algorithm-proof-exploration

<!--
@dependency-start
contract skill
responsibility Documents theorem-driven algorithm exploration before final formal proof adoption.
upstream design formal-proof-workflow.md checker-backed formal proof workflow.
upstream design computational-optimization.md numerical optimization contract workflow.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py builds JIT-canonical IR.
upstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
upstream design ../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop capabilities by frontier shape.
downstream implementation ../../.agents/skills/algorithm-proof-exploration/SKILL.md exposes the skill to Codex.
@dependency-end
-->

## Purpose

`algorithm-proof-exploration` は、証明義務を入力にしてアルゴリズムを探索・修正する
workflow です。対象は optimizer、solver、preconditioner、KKT 系、有限精度経路、
certificate-returning algorithm などです。

この skill は、実装から JIT-canonical IR、backend trace、Lean evidence module を作り、
target theorem に対してどの実装自由度、problem-class witness、数値収束 witness、
algorithm change が有効かを探索します。証明 route の採用、checker 実行、
counterexample / unprovable-under-assumptions claim の最終判定は
`$formal-proof-workflow` に渡します。
backend、runtime target、compiler route、device、dtype は、証明を通すために固定する
探索変数ではありません。user request、approved design、runtime profile、public API、
または config が明示した場合だけ backend 固有 theorem を扱います。それ以外では
backend を top-level profile input、generated backend witness、coverage evidence として
保持し、証拠不足は `backend_evidence_blocker` として返します。

## Use When

- アルゴリズムの収束性、停止性、certificate soundness、有限精度誤差、solver-chain
  handoff に対して、どのアルゴリズム構造なら証明義務を満たせるか探索したい
- 実装を証明可能な形に直すための algorithm choice / numerical convergence
  witness / problem-class witness を見つけたい
- `JIT-canonical IR`、backend trace、Lean evidence module、proof status overlay、
  algorithm blocker frontier を作る・更新する
- formal proof 側で閉じない場合に、どのアルゴリズム変更が必要かを整理したい

## Relationship To `$formal-proof-workflow`

- この skill は「アルゴリズム探索」を担当します。
  - root algorithm の JIT lowering
  - target theorem ごとの theorem graph/profile 作成
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
この skill から formal-proof subagent へ渡す `formal_proof_handoff` は、
`agents/COMMUNICATION_PROTOCOL.md` の `Target Binding Packet` を必ず含めます。
target theorem、public root / entrypoint と signature、theorem-visible return
projection、identifier naming plan、generated evidence artifacts、accepted top-level
assumptions、forbidden assumptions、completion condition、validation commands、
unchecked-output policy を埋められない場合は、曖昧な blocker summary を渡さず、
IR、theorem graph、または source packet を先に再生成・修復します。

## Numerical Iteration Boundary

反復型の数値 algorithm でも、最初の目的定理は public root の静的な引数 schema と
戻り値 schema で述べます。
典型的には `let out := main problem config` の `out.answer`、`out.state`、
`out.info`、またはそれらの field projection が停止時の KKT /
certificate soundness を満たす、という形です。その目的定理を分解した後にだけ、
`z_{k+1} = Step_impl(Problem, Config, z_k)` と
`R_impl(Problem, Config, z_k)` のような反復写像・停止スカラー補題へ降ります。
証明のために runtime proof check、diagnostic gate、`Info` field、
proof-only config/state を追加してはいけません。実行時にすでに返る値は theorem が
その値を対象にする場合だけ使い、証明用の値は IR、Lean 関数、lemma graph、または
`lean/lib` の有限精度モデルで再構成します。

現在の反復写像から target theorem が導けないことが checker-backed に分かった場合だけ、
code change を検討します。その変更は proof check を production code に入れることではなく、
initializer、update rule、line search、inner-solver policy、regularization、Phase I /
globalization などの algorithm そのものを、証明可能な反復写像へ置き換えることです。
変更後は IR、backend trace、Lean route、theorem graph、proof-status overlay を再生成し、同じ theorem に
戻って証明または反証まで進めます。

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
最小の algorithm change、problem-class witness、または generated backend coverage boundary として
採用します。
connection / bridge / profile binding / witness instantiation が開いている場合も
終了ではありません。その接続が caller lemma または target theorem edge を止めているなら、
function frontier と同じように再帰展開します。user-facing に返せるのは、残りが
production code / algorithm choice、`Problem` / config / solve-input の不足、または
backend/runtime architecture boundary へ縮約され、その最小性が checker-backed に
示された場合だけです。

## Canonical Flow

1. Target theorem:
   - 最初の target は JIT 可能な public entrypoint
     `main(problem, InitializeConfig, ...)` または同等の run 関数に対する
     全体命題です。`Answer` / `State` / `Info` の仕様から始め、下の項目は
     その全体命題を再帰分解して得られる theorem profile として扱います
   - 目的定理を低レベル op id、binding、region、frame、trace row、または
     generated evaluator の内部 state から作ってはいけません。public root の
     引数 tree と戻り値 tree を静的 schema として抽出し、`Answer` / `State` /
     `Info` field path から high-level projection 関数を生成して、その projection
     について theorem を述べます。低レベル IR は projection を実装 path へ展開する
     証拠です
   - local convergence
   - certificate soundness
   - finite-precision floor
   - solver-chain reachability
   - infeasibility / unboundedness certificate
   - problem-class narrowing
1. Root algorithm:
   - public `main` / run function
   - public `initialize` only as part of that run function's expansion
   - public `solve` only when it is the selected public root
   - one-step transition `step` only as a decomposition of the root theorem
   - certificate-returning function only when it is the public root
1. Operational algorithm assumption:
   - implementation-derived theorem では、抽出した root algorithm を
     `trace follows A_impl / Step_impl` という operational assumption として
     置く
   - convergence、certificate soundness、finite termination、residual
     reachability は、この operational assumption から導く lemma / theorem であり、
     assumption にしてはいけない
   - proof status overlay には `operational_assumptions` として記録し、
     `open_frontier` や backend coverage gap と混ぜない
1. JIT-canonical IR:
   - use `python3 tools/agent_tools/jit_canonical_ir.py --python-symbol <path.py::qualname> --input-factory <path.py::factory> --out <ir.json> --stablehlo-out <root.mlir> --backend-trace-dir <dir> --backend-trace-out <backend.json>`
   - extract StableHLO, thin operational op kinds, dtype coverage, backend phase traces, and LLVM typed traces when the backend reaches LLVM
   - do not add recursion-depth knobs or hand-written implementation equations to change proof conclusions
   - generate checker-facing Lean evidence modules with `tools/bin/agent-canon jit-ir-to-lean`
   - keep the generated evidence layer separate from the theorem dependency graph. The generated layer owns root identity, StableHLO hash, operational op kinds, dtype coverage, and backend trace coverage. The proof graph owns theorem propositions and dependency edges. A route like `theorem X by A, B, f` is accepted only when `f` resolves to a current generated evidence row, generated code-graph function, or trace produced by the active lowering route.
   - require the lowering / projection layer to expose public-root argument
     schema, return schema, return leaf indexes, and high-level projection
     functions for theorem-visible return fields. If those projections are
     missing, fix extraction or the `main` return shape before exploring
     theorem-specific low-level facts
1. Algorithm Flowchart:
   - use `$algorithm-flowchart` after IR and theorem-graph generation when a
     human or agent needs to see the implemented iteration path and proof-state
     overlay at once
   - render from IR / theorem graph / `proof_status.json`, not from a hand-drawn
     diagram
   - use `--view runtime` or `--view core --include-code-facts` when the
     artifact must show implementation flow without proof-only branches or
     labels
   - treat the Mermaid chart as navigation evidence only. It may show where a
     block is verified, open, or external, but proof completion still comes from
     `$formal-proof-workflow` checker evidence and theorem graph validation
1. Equation projection:
   - after theorem graph generation, use the JIT-canonical evidence slice and
     theorem graph checker for theorem-critical assignment and return equations
   - check iteration slices by `source_symbol` and `equation_tags`, for example
     `step_update`, `reduced_kkt`, `minres_defaults`, and initialization tags
   - if an equation fact is absent from the graph or lacks a
     `lemma_consumes_code_fact` edge, fix IR extraction or graph generation
     before writing proof prose or Lean bridge lemmas
   - for target-critical equation sections, use the relevant projection tool
     with the current JIT-canonical IR files and theorem graph overlay
   - if the generator fails because a required code fact is missing, classify
     the gap as IR extraction weakness or code-shape opacity before writing
     proof prose
   - displayed implementation formulas in that section are substituted from
     matched IR `code_facts[*].expression`; proof notes should link to the
     generated section instead of carrying parallel hand-written runtime
     equations
  - theorem-critical IR equations must be propositionized from the current
    target proposition `P`, where `P` is stated over public-root return
    projections rather than low-level facts. Select the target theorem/profile
    in the Lemma Dependency Graph to bound the search surface, then build a
    target-rooted substitution tree from the `Answer` / `State` / `Info` field
    path consumed by `P`. That tree first follows the static return projection
    to return leaf indexes and then recursively follows local assignment and
    callee return equations. Bridge candidates are scoped to that
    projection-rooted substitution tree. Runtime
    observation / diagnostic / logging paths are not hard-coded as included or
    excluded: if `P` is about their validity, they are the root; if `P` is
    about a solver return or residual decrease and they are not assigned into
    that value, they remain execution evidence outside the substitution tree.
    IR extraction tells which equations are present; target proposition-tree
    search tells which of those equations matter for the current theorem. This
    skill explores which bridge proposition is useful for the target theorem.
    Do not freeze on one bridge shape. Generate multiple bridge candidates at
    the abstraction level required by the target theorem, check or refute them
    when possible, and classify each candidate before choosing the next route.
    Do not leave theorem-critical returned values unconstrained when the
    current IR contains equations that determine or bound them.
   - candidate selection is recursive and target-driven. State the current
     target proposition `P`, run checker/tactic search such as `aesop?`,
     inspect unsolved subgoals or missing hypotheses, translate those gaps into
     bridge candidates, check whether current Lean functions / generated IR
     facts prove or refute each candidate, and rerun the proof of `P`. Repeat
     until `P` is proved, refuted, shown unprovable under the current top-level
     assumptions, or reduced to a strictly smaller named witness. A flat
     candidate list is only input to this loop.
  - 候補条件が `P` と定義的に同じ predicate であるためにだけ証明できる場合は、
    `projection_only` / `circularity_check` と分類します。これは theorem surface
    の投影証拠であり、algorithmic success や `Problem` 条件ではありません。
    frontier は、`P` を真にする非循環 mechanism、すなわち実装 recurrence の
    residual reachability、finite ranking、contraction/decrease、またはそれを
    含意する problem-class witness へ進めます。
    循環性は theorem 名や predicate 名の語彙ではなく、命題グラフ上の到達可能性で
    判定します。conclusion 側から definition / projection / equivalence /
    existential-lift / certificate-inclusion edge を辿って、独立条件として採用したい
    problem class や certificate に戻る route は、名前を変えていても
    `circularity_check` です。
1. Algorithm frontier extraction:
   - choose graph frontier nodes by their algorithmic impact, not prose order
   - normalize each target-facing blocker to implementation identity,
     returned-value projection, numerical reachability/ranking mechanism,
     algorithmic choice, external assumption binding, or problem-class witness
   - do not treat a failed single-lemma route as an algorithm failure. Hand
     proof-route alternatives to `$formal-proof-workflow`; this skill uses the
     returned proof outcome to decide whether an algorithm change is needed
  - when formal-proof returns a missing witness or assumption-insufficiency
    result, decide whether that gap is better solved by changing the algorithmic
    recurrence, deriving a numerical convergence witness, narrowing the problem
    class, or leaving an external assumption boundary
  - frontier を、対象アルゴリズム入力と無関係な仮定注入で閉じてはいけません。
    固定された algorithm では、数学的仮定は theorem top level の
    `Problem` と config object にだけ置きます。途中で必要になる主張は仮定ではなく
    `top_level_problem_config_lemma` のような problem/config-derived lemma として持ち、
    その top-level 仮定と抽出済み code path から証明します。
    implementation trace や backend/runtime semantics のような architecture
    assumption は許可しますが、Problem/config assumption とは別ラベルにします。
  - proof graph 構造解析では、projection evidence と numerical progress evidence を
    分離します。`Condition := Target -> Target` という path は connected でも
    循環です。`circularity_check` として保持し、`Problem`、config、generated
    code facts、backend profile、または formal-library theorem から condition を導く
    別の非循環 edge が入るまで、finite-stop / convergence の certified subgraph に
    採用しません。
    この除外は graph-based です。target / conclusion node から proof-consumption edge を
    辿り、独立条件として採用したい node に到達するかを見ることで判定します。
    語彙検査だけで「非循環」と判断してはいけません。
  - ほしい局所仮定は premise ではなく導出 target として扱います。各中間条件に
    candidate lemma 名を付け、すべての変数を `Problem`、config、IR が抽出した
    path state、code fact、または許可された architecture boundary のどれかへ
    束縛してから、`$formal-proof-workflow` へ渡して top-level 仮定と code path
    から導けるかを試します。失敗した場合は、theorem を緩める前に lemma 形状を変えます:
    quotient / projection、上界補題、selected-scope bound、finite-prefix
    ranking / contraction witness、same-units conversion、既存の algorithm return
    fact の projection を試します。ほしい条件を独立仮定に昇格してはいけません。どの導出 route も
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
  - if the returned witness is a connection-level guarantee whose absence
    blocks a caller lemma or target theorem edge, handle it as a recursive
    frontier too. Examples are a code fact not yet bound to a theorem variable,
    a solver-return unit conversion, a backend profile instance, or a bridge
    lemma edge. Do not classify it as algorithmic progress until the connection
    is verified, refuted, proved unprovable under current top-level assumptions,
    or reduced to a minimal code/input/backend boundary with checker evidence
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
     `<inner_solver> cannot guarantee requested residual for the current
     transformed operator -> <caller_solver> cannot bound returned direction
     error -> <outer_step> cannot prove the target residual/certificate property
     -> finite reachability remains unproved`.
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
   - local / partial counterexample を `guarantee_refuted` として採用する前に、
     current public `main` / run path、target `Problem`、config、backend
     assumptions から、その counterexample が使う local state / input / model /
     trace へ到達する embedding theorem を証明します。さらに、その local falsification が
     caller lemma と target theorem edge を壊す propagation edge も証明します。
     どちらかが未接続なら、その artifact は
     `local_counterexample_candidate` または
     `route_rejected_not_top_level_reachable` として failed-route overlay に残し、
     user-facing refutation ではなく recursive frontier の作業対象に戻します。
   - do not return user-facing progress with a function guarantee still marked
     `guarantee_unconnected` when that unconnected guarantee is the reason a
     caller-side lemma or target theorem edge is open.  Re-enter the recursive
     function frontier immediately: generate the next callee/function property,
     prove it, refute it, prove it unprovable under the current top-level
     assumptions, or change the algorithm and regenerate IR/graphs.  A smaller
     named witness is not a user-facing stopping point for this class of gap;
     it is the next in-turn work item.
   - the same rule applies to `connection_unconnected`: bridge edges, profile
     bindings, unit conversions, return-value substitutions, and
     theorem-variable instantiations are work items, not reports. Expand them
     through IR equations, Lean route functions, graph overlays, `lean/lib`
     profiles, source packets, or backend assumptions until the connection is
     terminal or the remaining boundary is a checked code/input/backend issue.
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
   - keep the implemented trace as the operational assumption. New bounds,
     ranking/contraction witnesses, and projection lemmas must be derived from
     the extracted code path and theorem variables, not from proof-only
     production fields
1. Algorithm change guidance:
   - remove unsound gates
   - change an algorithmic choice only when the proof obligation shows that the
     current choice blocks the theorem
   - replace the current recurrence, initializer, line-search, inner-solver
     policy, regularization, Phase I, or globalization route with a provable
     numerical mechanism when the current one is refuted or insufficient
   - replace hard-coded initial points with a proof-visible selected initializer
     when the target theorem needs basin/selected-scope entry, and state whether the
     remaining proof obligation is on `Init(Problem, InitializeConfig)` or on a
     stronger Phase-I/globalization algorithm
   - add Phase I / globalization when the theorem needs basin entry
   - narrow a theorem to selected local scope / warm-start assumptions
   - add problem-class or backend evidence witnesses
1. Formal proof handoff:
   - pass exact theorem variables, proof artifacts, checked fragments, and remaining obligations to `$formal-proof-workflow`
   - include the complete `Target Binding Packet`: target theorem, public root,
     return projection, identifier naming plan, generated evidence, accepted /
     forbidden assumptions, completion condition, validation commands, and
     unchecked-output policy
   - do not mark a graph path verified unless checker-backed proof nodes cover the target chain

## Artifact Contract

Use these names in run bundles, proof notes, or `lean/<proof-theme>/` artifacts:

- `proof_jit_canonical_ir`: source root, target theorem, operational ops, backend traces.
- `proof_lemma_graph`: target chains and dependency edges.
- `proof_operational_assumptions`: extracted implemented-algorithm trace
  premise, such as `trace follows A_impl / Step_impl`.
- `proof_algorithm_flowchart`: Mermaid or Markdown diagram generated from the
  current JIT-canonical IR, theorem graph, and proof-status overlay.
- `algorithm_frontier`: current algorithmic blockers, candidate changes, and
  handoff targets.
- `algorithm_change_guidance`: implementation changes needed for provability.
- `formal_proof_handoff`: exact claims and checker commands for `$formal-proof-workflow`.

## Guardrails

- Do not prove Pyright/type facts unless they are mathematical dependencies of the target theorem.
- Do not add proof-only production config or state.
- Do not add runtime proof checks, proof-only `Info` fields, or diagnostic gates
  solely to satisfy a proof obligation.
- Do not treat IR or graph reachability as proof completion.
- Do not treat convergence as an assumption. The implemented algorithm trace is
  the assumption; convergence is the lemma derived from that trace plus
  problem/backend witnesses.
- Do not treat one failed formal-proof route as an algorithmic blocker until
  `$formal-proof-workflow` has checked whether a weaker or bundled route can
  close the target.
- Do not split one proof theme across competing proof notes. Implementation path explanation may live in Design docs; mathematical proof text belongs in `notes/themes/`.
