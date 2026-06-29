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
upstream implementation ../../tools/agent_tools/lean_proof_env.py creates Lean proof-search, theorem-search, and counterexample environments.
upstream design ../../documents/tools/lean_capability_matrix.md routes Lean/Mathlib/Aesop/Plausible/LeanSearchClient capabilities by proof-frontier shape.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived thin operational IR and backend traces.
upstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts C++ source-canonical IR into thin operational IR.
upstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders thin operational IR into Lean evidence definitions.
upstream implementation ../../tools/agent_tools/cpp_template_to_lean.py fully expands C++ template roots into Lean evidence.
upstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant references.
downstream implementation ../../.agents/skills/formal-proof-workflow/SKILL.md exposes the skill to Codex.
@dependency-end
-->

## Reader Map

- Purpose: formalize mathematical, proof-sketch, and implementation-derived
  claims into checker-backed proof or refutation routes.
- Section path: start with Purpose, Use When, Core References, and Mandatory
  Checklist; then use Canonical Flow, Required Outputs, Proof Status Table,
  JIT-canonical IR, Lemma Dependency Graph, Frontier Exploration Loop, and the
  proof-expansion sections for operational detail.
- Use when: a claim needs Lean/Isabelle/Coq/SMT evidence, proof-search
  scaffolding, theorem-graph routing, or generated implementation evidence.
- Boundary: natural-language proof text, unchecked theorem files, and
  `blocked` / `unverified` states are not final proof evidence.

## Purpose

自然言語の数学的主張、証明スケッチ、設計上の lemma、または
JIT 正本から抽出した実装由来証明候補を、形式証明へ進めるための workflow です。
この skill は、claim を assumptions / definitions / theorem target /
proof obligations / existing proof search / checker command に分解します。
最終目的は、target claim を checker-backed に証明するか、同じ claim が
現在の仮定・実装経路からは証明できないことを反例、独立性、または
仮定不足 witness によって示すことです。
LLM 生成文、自然言語証明、未検査の theorem file を証明済みとは扱いません。
`blocked`、`not_run`、`unverified` は途中状態であり、skill の完了判定では
ありません。
実装由来の claim では、skill の返却単位は `code path -> theorem` です。
未接続の theorem graph edge、`next_witness`、未展開の generated equation、
未接続の generated Lean 関数、または repairable extractor gap が残る場合、
それは user-facing outcome ではなく同一 Wave の work item です。実装由来の
Goal では、`verified` / `refuted` / `unprovable_under_assumptions` /
checked boundary を top-level 分岐として返してはいけません。個々の proof row
の checker status は Goal checklist の check item であり、user-facing outcome
はその checklist 全体の `pass` / `fail` と、失敗した required item の一覧です。
必要な check item は proof search 中に増やせますが、未接続 item を別 branch の
完了扱いにしてはいけません。

## Use When

- 文書や設計にある数学的 claim を Lean、Isabelle/HOL、Coq/Rocq、SMT などへ形式化したい
- 既存 formal library に theorem や lemma があるかを先に探したい
- proof assistant を使う前に proof obligation、前提、定義不足を棚卸ししたい
- 論文、scholarly note、optimization / numerical method design の理論 claim を検査可能な形に落としたい
- 実装前に Lean で設計されたアルゴリズム claim を最終 proof artifact として採用したい
- JIT 可能な Python 実装 root から StableHLO/backend trace 由来の generated Lean evidence と theorem graph を作りたい
- C++ template algorithm root から full-expansion route で generated Lean evidence を作りたい

## Core References

- `agents/skills/literature-survey.md`
- `agents/skills/academic-writing.md`
- `agents/skills/long-form-writing.md`
- `agents/skills/report-writing.md`
- `agents/skills/research-workflow.md`
- `agents/skills/paper-writing.md`
- `agents/skills/lean-algorithm-design.md`
- `agents/skills/algorithm-proof-exploration.md`
- `documents/tools/formal_proof.md`
- `documents/tools/lean_capability_matrix.md`
- `references/agent-canon-technology-bibliography.md`

## Mandatory Checklist

- 形式化前に、claim、assumptions、definitions、target theorem、proof sketch を分けます。
- 実装由来のアルゴリズム claim は、必ず実装正本の public entrypoint に対する
  全体命題から始めます。JIT route では
  `main(problem, InitializeConfig, ...)` または同等の run 関数、C++ source route では
  `cpp_template_to_lean.py --cpp-symbol` で選んだ C++ template root を public root
  として扱います。戻り値 `Answer` / `State` / `Info` の仕様、または C++ root から
  生成した public-interface / source-fact projection を target theorem にし、
  補助定理、内側 solver、loop-control、残差成分、局所収束命題は、その全体命題を
  再帰分解して必要になった場合だけ選びます。
- 実装由来 claim の `program contract` は、public entrypoint、入力 schema、
  runtime profile、return projection、observable effect、assumptions /
  preconditions、checker / validation command を束ねた入口です。theorem target、
  proof obligation、reader-facing proof note はこの契約から射影します。
- 数学的判定は `mathematical necessity gate` を通します。theorem surface、
  proof obligation、accepted assumption、counterexample obligation、
  checker-backed validation command は、public entrypoint と program contract から
  射影した必要性を持つ場合に採用します。補助 lemma や局所判定は、target theorem の
  dependency graph 上で必要な場合に選びます。
- 目的定理は public entrypoint の静的な引数 schema と戻り値 schema から作ります。
  低レベルの op id、binding、region、frame、trace row、または
  `generatedMainFuel` の内部 state を目的定理の表面にしてはいけません。
  典型形は `let out := main problem config` の `out.answer`、
  `out.state`、`out.info`、またはそれらの field projection について述べる定理です。
  低レベル IR / generated Lean evaluator は、その projection がどの実装 path から
  得られたかを再帰展開して証明するためだけに使います。
- JIT proof root の `main` は、数学的に調整可能な入力を public arguments として
  集約します。通常は `Problem`、`InitializeConfig`、必要なら runtime の
  `SolveConfig` など実行時 API に実在する入力だけです。proof-only 引数、proof-only
  config/state、低レベル trace handle、op id、binding id を `main` に追加して
  theorem を通してはいけません。証明に必要な可観測値は `Answer` / `State` /
  `Info` の静的 field、または theorem graph が実装 path から再構成する値として
  扱います。
- formal proof work を subagent に渡す場合は、`agents/COMMUNICATION_PROTOCOL.md`
  が所有する `Target Binding Packet` を handoff に含めます。file list
  だけで「証明を見て」「blocker を探して」と渡してはいけません。unchecked theorem
  sketch、型が合っていない statement、public root への到達が示されていない local
  counterexample、algorithm suggestion は、同じ public root と theorem surface に対する
  checker / validation が通るまで採用しません。
- 実装由来 proof task では、user-facing return の前に親以外の read-only agent または
  checker tool に state inspection を実行させます。inspection packet には target
  theorem、public root / signature、return projection、theorem graph board、proof
  status、generated evidence、exit-gate criteria、今回の user target を含めます。
  inspector は新しい theorem を作るのではなく、`complete` / `boundary_reached` /
  `interim_status` の分類が skill contract と artifact に一致するかだけを検査します。
  親は inspector の finding を graph / proof-status / tool output に反映し、同じ
  exit gate を再実行してから返答します。inspection が未実行、または finding が未反映の
  状態で `verified`、`finite stop achieved`、`Goal complete` などを user-facing に
  書いてはいけません。
- IR-to-Lean / theorem-graph tooling は、public root の引数 tree、戻り値 tree、
  `Answer` / `State` / `Info` などの field path、return leaf index の対応を
  生成しなければなりません。目的 theorem はこの high-level projection 関数だけを
  参照します。projection から低レベル evaluator への接続が欠けている場合は、
  低レベル binding を目的定理へ持ち込まず、extractor、projection 生成、または
  `main` の返却 schema を直します。
- theorem-critical な値は、自由 witness ではなく、public root の入力と実装 path から
  生成された値として扱います。たとえば KKT 成分、残差成分、停止 tolerance、
  solver 返却値、backend decode 誤差を target theorem が消費するなら、生成 Lean には
  `def valueOf(problem, config, ...)`、projection lemma、または lookup 決定性 lemma の
  いずれかが必要です。`Nonempty ... values` や任意 record だけで上界条件を
  閉じてはいけません。存在 witness を使う場合は、同じ public input と generated
  state から得られる二つの witness が一致する uniqueness theorem、または witness を
  生成関数へ置き換える theorem を先に通します。この gate が失敗したら、証明
  blocker ではなく extractor / projection / generated Lean の修正対象です。
- 実装由来の claim は、実装正本に合う機械抽出 route を先に固定します。
  JIT 可能な Python public root は
  `jit_canonical_ir.py --python-symbol path.py::qualname --input-factory path.py::factory`
  で StableHLO と backend trace へ lower します。C++ template algorithm を
  source of truth にする場合は、
  `cpp_template_to_lean.py --cpp-symbol path.hpp::qualname --namespace <Lean.Namespace>`
  で C++ source envelope、完全展開済み `agent-canon.thin-operational-ir.v2`、
  Lean evidence definitions を一つの tool route で生成します。どちらの lowering 結果も
  proof artifact の入口ですが、それ自体は semantic proof ではありません。
- backend、runtime target、compiler route、device、dtype を theorem や validation
  claim を通すために固定してはいけません。backend 固有 theorem は、user request、
  approved design、runtime profile、public API、または config がその backend を
  明示した場合だけ有効です。それ以外では backend semantics を top-level profile
  input、generated backend witness、coverage evidence として保持し、証拠不足は
  `backend_evidence_blocker=<gap>` として記録します。IREE、XLA、CUDA、CPU、GPU、
  VMFB、StableHLO、LLVM、FP32 などへ theorem を縮退させて主張を成立させてはいけません。
- アルゴリズム由来の claim で、証明 path 探索、algorithm change の判断、
  IR / lemma graph / frontier overlay の更新が必要な場合は、先に
  `$algorithm-proof-exploration` を使います。この skill は、その探索結果を
  theorem statement、checked fragment、counterexample、unprovable-under-assumptions
  witness として採用する段階を担当します。
- 実装前のアルゴリズム設計 claim では、先に `$lean-algorithm-design` を使います。
  この skill は、そこで checker-backed に検証された Lean 定義、target theorem、
  refutation、または restricted problem class を proof artifact として採用する段階を
  担当します。
- アルゴリズム由来の claim では、局所証明を選ぶ前に root algorithm を
  選択済み route の機械抽出 evidence として保持します。JIT route では
  StableHLO function/control/backend-trace edge から JIT-canonical IR を作り、
  C++ source route では source envelope、source facts、thin operational IR の
  function/region/op/edge を作ります。IR は proof ではなく、最終命題に必要な
  局所 theorem / lemma だけを選ぶための中間表現です。
- algorithm update が初期値選択、cold start、Phase I、basin entry、selected-scope entry を
  変更した場合は、ユーザーへ返す前に IR / lemma graph / proof-status overlay を
  再生成し、初期化経路から機械抽出できる code fact をすべて採用候補へ接続します。
  例: `z_init`、`x_init`、slack / multiplier floor、initial residual、
  epigraph 変数、初期 KKT state の由来。これらを「コードを読めばわかるはず」として
  blocker に残さず、checker-backed fragment、code-derived fact、または graph edge として
  記録します。
- 初期値証明では、実装が数学的に要求しない限り `z_init = 0` を theorem premise に
  しません。証明はまず `z_init = Init(Problem, InitializeConfig)` という
  code-selected initializer として正規化し、IR の code fact が本当に zero initializer を
  示す場合だけその特殊化を使います。zero が単なる現在の実装選択であり theorem を
  制限ているなら、problem-class witness または algorithmic choice として
  `$algorithm-proof-exploration` に戻します。
- 実装由来 IR は、JIT route では `python3 tools/agent_tools/jit_canonical_ir.py`、
  C++ source route では `python3 tools/agent_tools/cpp_template_to_lean.py`
  で full-expansion record と generated Lean evidence を作成し、
  `proof_algorithm_ir`、`proof_goal_directed_slice`、
  `proof_selected_local_obligations` として proof note または run artifact に残します。
- checker 向けの実装 path evidence は、JIT-canonical IR では
  `tools/bin/agent-canon jit-ir-to-lean` で Lean evaluator / code graph artifact を
  生成し、C++ source route では
  `python3 tools/agent_tools/cpp_template_to_lean.py` で
  `OperationalFunction`、`OperationalRegion`、`OperationalOp`、
  `ExpansionEdge`、`CodePath`、`CodePathDecision`、`OperationalCoverage`
  などの Lean evidence definitions を生成します。
  C++ route は unresolved call target、unassigned op、または code-path row を持たない
  reachable function を Lean 出力前に拒否します。
  Generic operational IR renderer は Lean 関数 lowering や
  `ImplementationFunction` / `FunctionTrace` / `CodeEquation` schema を主張しません。
  IR の operation tree と source facts で evaluation order と branch / loop 形状が
  得られる場合でも、手書きの algorithm-specific operation record を新しい proof
  entrypoint にしてはいけません。
  構造体アクセスは IR 後段の projection pass で正規化し、proof theme 側は生成
  evidence を provenance として消費して型付き補題を別に与えます。生成 evidence と
  proof graph は別物です。code path が Lean 関数へ完全に lower されたと主張する前に、
  JIT-specific generator では生成 Lean module の
  `generated_function_lowering_coverage_verified` を checker で通し、generic
  operational IR renderer では generator が complete coverage を既定で要求し、
  `coverageComplete = true` の generated evidence を出したことを evidence に含めます。生成名の
  text-search 確認や prose inspection だけを coverage evidence として採用してはいけません。
  proof graph は proposition と theorem dependency edge を持ちます。`theorem X by A, B, f`
  のような route は、`A` と `B` が proof premise、`f` が JIT-generated code graph
  上の implementation function / trace、または generic operational evidence から
  明示的に構成された projection lemma に埋め込める場合だけ採用できます。
- 実装由来の theorem は、実装 path が使っているデータ型、またはそのデータ型からの
  明示的な decoded view の上で述べます。implementation residual、status、solver
  answer、finite-precision value、certificate を、証明しやすい `Nat`、`Real`、
  unconstrained record などへ置き換えてはいけません。ただし、実装 path がその型を
  実際に使っている場合、または coercion / decode / unit conversion / projection を
  IR fact と Lean theorem で証明している場合は使えます。有限精度実装では、runtime
  値が満たさない field abstraction ではなく、丸め値モデルと `decode` 関係の上で
  arithmetic claim を証明します。
- 反復型の数値 algorithm の収束 claim は、実装された反復写像と停止スカラーを
  直接 theorem にします。典型形は
  `z_next = Step_impl(Problem, Config, z)` と
  `R_impl(Problem, Config, z)` から、縮小性、ranking、有限到達性、または停止時の
  KKT / certificate soundness を導く形です。証明のために production runtime へ
  proof check、diagnostic gate、proof-only `Info` field、proof-only config/state を
  追加してはいけません。現在の写像で証明できないことが checker-backed に分かった
  場合だけ、`$algorithm-proof-exploration` へ戻して initializer、update rule、
  line search、inner-solver policy、regularization、Phase I / globalization などの
  algorithm 自体を証明可能な反復写像へ置き換えます。
- target-critical solver-chain の数式 section は、現在の JIT-canonical record
  と theorem graph overlay から生成します。必須の equation evidence が欠けて
  projection が失敗した場合は、proof note を手書きで補わず、JIT 抽出または実装形状を
  直してから再生成します。proof note 側に同じ runtime 数式を並行して手書きしません。
- 命題化は flat な fact 一覧ではなく、public root の戻り値 projection で述べた
  目的命題 `P` から始めます。まず Lemma Dependency Graph の
  target theorem/profile で探索 surface を bounded にし、次に `P` が参照する
  `Answer` / `State` / `Info` field path から static return projection tree を作ります。
  projection tree を低レベル return leaf へ接続した後で、local assignment と
  callee return equation を再帰的に辿ります。bridge candidate 抽出では、
  この projection-rooted tree に含まれる fact だけを候補化します。
  runtime observation / diagnostic / logging path は
  一律に除外しません。`P` がそれらの妥当性なら tree root として採用し、`P` が solver
  return / residual decrease なら、その戻り値に代入されない観測 path は substitution
  tree 外の execution evidence として扱います。
- 定義だけで閉じる proof route は、採用前に循環性として分類します。候補となる
  "必要十分条件" が `Iff.rfl`、`rfl`、または target predicate を同じ
  stop / reachability predicate へ unfold するだけで閉じる場合、その theorem graph node は
  `circularity_check` または `projection_only` です。これは theorem surface を
  正しく投影できた構造証拠ですが、substantive な `Problem` / config 条件でも
  finite-stop / convergence proof の完了でもありません。次 frontier は、その投影が
  露出した非循環命題、典型的には実装 recurrence の residual reachability、
  ranking / contraction、またはそれを導く problem-class witness です。
  循環性は theorem 名、predicate 名、`certified` などの語彙ではなく、命題グラフの
  到達可能性で判定します。conclusion node、certified-convergence node、または proposed
  iff side から、definition / projection / equivalence / existential-lift /
  certificate-inclusion edge を辿って、独立条件として採用したい problem class、
  stop predicate、certificate、quantitative bound に到達するなら、その route は
  `circularity_check` です。名前が違う場合や Lean proof が単一の `rfl` でない場合も、
  graph が到達すれば convergence / finite-stop の必要十分条件として採用してはいけません。
- target theorem / profile を完了扱いにする前に、leaf-origin check だけでなく
  forbidden-reachability check を graph に設定して実行します。対象 target から
  `open_frontier`、`frontier`、`unverified`、または同等の status / kind node に
  到達できる場合、終端 leaf が許可 origin に落ちていても未完了です。その reachable
  frontier を Wave の作業リストとして、`verified`、`refuted`、
  `unprovable_under_assumptions`、または下位 checker 済み boundary まで
  再帰的に進めます。
- backend / dtype / IREE / finite-precision semantics は production code や
  `InitializeConfig` へ proof-only field として足さず、JIT-canonical IR の
  `backend_assumptions` と Lemma Dependency Graph overlay に theorem variable /
  witness obligation として保持します。
- bridge、connection、profile binding、witness instantiation は frontier そのものとして
  再帰展開します。caller-side lemma や target theorem edge を止めている
  接続行を、単なる「未接続」「今後接続」として user-facing に返してはいけません。
  その接続が code fact、generated Lean evidence、checker-facing Lean 関数、
  lemma graph、`lean/lib` profile、backend/source packet から導けるなら、
  証明または反証まで進めます。返せるのは、
  残りが production code / algorithm choice の問題、`Problem` / config / solve input の
  不足、または現在の repository / tool 環境では進められない backend/runtime
  architecture boundary であることを checker-backed に示した場合だけです。
- ユーザーが「足りない部分」「どこが未接続か」「なぜ証明できないか」を聞いた場合も、
  未接続 edge 名や追加 lemma 名を終端回答にしてはいけません。まず同じ public-root
  theorem の Goal checklist に required item を追加し、その item を
  `verified`、`refuted`、`unprovable_under_assumptions`、checked boundary、または
  selected route から pruned のいずれかへ落とします。説明は、その checked item から
  production code / algorithm choice、`Problem` / config / solve input、または
  backend/runtime architecture boundary へ至る因果鎖として返します。
- 実装由来の証明タスクの返却単位は常に「code path -> theorem」です。未証明の
  追加定理、bridge lemma、witness 名、または「この補題が必要」という列挙を
  user-facing な終端結果にしてはいけません。必要な定理が current code path と
  public input から導けるなら、その場で証明して graph に接続します。導けないなら、
  どの production 実装機構、抽出器、generated Lean 関数、theorem graph wiring、
  `Problem` / config 入力条件、または backend 境界が原因で target theorem が
  閉じないのかを checker-backed な因果鎖として返します。証明を成立させるための
  次の「追加定理」は、実装上の問題を特定する中間 witness であって、ユーザーへの
  final answer ではありません。
- runtime `Info` はランタイムで使う診断・収束判定・ログに限定し、証明用 witness を
  追加してはいけません。証明に必要な値は `Problem + InitializeConfig + State_k`
  と実装 path から proof extractor / lemma graph 側で再構成し、必要なら
  `runtime_value <= upper_bound <= requested_budget` の上界補題として扱います。
  反復ごとに KKT 条件数を評価することは一つの検証 route にすぎず、選択された局所 scope 上の
  一様 regularity / preconditioner / slack-floor certificate で各 `k` の witness を
  補完できる場合はそれを優先します。
- 採用する仮定は必ず対象アルゴリズムの入力に接地します。実装由来の
  algorithm theorem で許される非 code premise は、対象 `Problem` の性質、
  対象 config object の数値選択、IR から抽出した operational trace や選択
  backend/runtime profile のような architecture assumption、または formal library
  theorem に限ります。`State_k` のような path state は `Problem + Config` の trace が
  生成した値としてだけ使い、独立注入仮定にしてはいけません。任意の residual map、
  抽象 direction、自由な selected scope、proof-only state、diagnostic-only field
  など、対象入力でないものへの仮定を置いてはいけません。中間で必要になる主張は
  仮定ではなく補題です。トップレベル仮定と抽出済み code path から証明し、途中で
  新しい独立仮定として注入してはいけません。機械分類では
  `top_level_problem_config_lemma` のような problem/config-derived lemma として持ち、
  `Problem + Config` と生成 path から導く lemma / witness へ書き換えるか、強すぎる theorem を `refuted` /
  `unprovable_under_assumptions` として分類します。Algorithm-specific な注入仮定は、
  対象 algorithm の public input object と configuration object に限定し、実装 trace と
  backend/runtime semantics は architecture assumption として分けます。
  最適化問題で「微分可能」と言う場合は、対象 `Problem` の目的関数・制約関数の
  微分可能性だけを指します。residual sequence、更新則、proof-introduced helper の
  微分可能性を代替仮定にしてはいけません。
- checker 向け中間表現、lemma graph、profile library、generated Lean file は
  `lean/<proof-theme>/` に置き、再利用する profile / arithmetic library は
  `lean/lib/` に置きます。profile library を読むのは
  `jit_canonical_ir.py` などの証明ツールであり、production algorithm は
  読みません。reader-facing な証明本文は `notes/themes/` を正本にし、`lean/` には
  機械可読 artifact と checker artifact を置きます。
- JIT-canonical IR から theorem graph を作成し、`proof_lemma_graph`、
  `proof_target_chains`、graph validation evidence として proof note または
  run artifact に残します。IR は実装展開、lemma graph は命題依存を表し、
  両者を混ぜて `verified` claim を作ってはいけません。
- theorem-critical な中間計算式を証明 fragment が消費する前に、
  theorem graph checker を使い、
  IR の `assignment_equation` / `return_equation` が lemma graph の
  code-fact node、`lemma_consumes_code_fact` edge、target chain、必要なら
  `proof_status.json` の `code_derived_facts` に対応していることを検査します。
  反復単位の式は `source_symbol` と `equation_tags` で slice し、式を Lean や
  proof note に手書きで散らす前に、IR 由来の式として graph に固定します。
- theorem-critical な IR 式は、public-root projection で述べた目的命題 node から
  Lemma Dependency Graph の target chain を探索して候補化します。まず target
  theorem / target profile を選び、`Answer` / `State` / `Info` field path から
  static return projection、return leaf、低レベル code fact へ順に到達する node だけを
  bridge candidate の母集団にします。chain 外の式、未代入 call edge、
  `substitution_eligible=false` の fact は、到達や観測の evidence であっても
  最初の proposition 候補にはしません。LLM はこの target-reachable fact set から
  複数の数理 bridge 候補を作り、typed Lean proposition と theorem に昇格します。
  IR は式の所在を示し、Lean proposition はその式の数学的意味の候補を述べます。
  target theorem に必要な抽象度で複数候補を作り、可能なら checker で証明または
  反証し、候補ごとに分類してから次の route を選びます。現在の IR が決定または
  上界付ける theorem-critical な返却値を unconstrained variable のまま残す状態を
  完了扱いにしてはいけません。
- algorithmic blocker を user-facing に返す前に、target theorem に向かう
  algorithm route 全体を命題化します。反復 solver では最低限、停止 scalar、
  state update、step length / acceptance selection、direction construction、
  nested solver の返却値 / certificate、residual / merit recomputation、final scalar
  binding を theorem-specific な Lean proposition にするか、IR がそれを露出できないことを
  checker-backed に示します。「関数Aが関数Bを呼ぶ」という route fact だけでは、
  B の返す値が target theorem に効く場合の完了扱いにしてはいけません。残る frontier は
  contraction theorem、residual-merit selection、problem-class analytic bound、
  backend boundary、checker-backed refutation などの semantic mechanism まで縮約します。
  target path 上に未命題化の generated equation が残っているなら、それを先に消費します。
- 候補選択は再帰的かつ target-driven に進めます。現在の最終命題 `P` を立て、
  `aesop?`、`aesop`、`simp?`、`exact?`、または Lean capability route を実行し、
  未解決 goal / missing hypothesis を読みます。その gap を bridge candidate に翻訳し、
  generated Lean evidence、checker-facing Lean 関数、IR/source fact から
  証明または反証できるか確認し、再び `P` の証明を走らせます。
  `P` が証明・反証・現仮定下での非導出証明・下位 witness への縮約のいずれかに達するまで
  ループします。平坦な候補一覧はこのループの入力であり、最終成果ではありません。
- 実装されている反復法と証明状態を人間が一目で確認する必要がある場合は、
  `$algorithm-flowchart` で IR、theorem graph、
  `proof_status.json` から Mermaid chart を生成します。図は proof path の
  navigation evidence であり、`verified` claim の authority ではありません。
- 生成された補題群は selected route の IR/source envelope と generated Lean
  evidence から出てくるものとして扱います。
  アルゴリズム変更後は fingerprint で旧補題を識別せず、IR、graph、
  proof-status overlay を現行 root から再生成します。旧root由来のIR-backed
  補題や採用済み overlay を持ち越してはいけません。
- Lemma Dependency Graph は証明探索の編集対象です。機械生成された
  IR-backed obligation は source program の変更に伴う IR 再生成でだけ同期し、
  agent / human が追加する
  補助命題、dependency edge、proof attempt、採用 / 棄却理由は
  graph overlay として provenance 付きで残します。探索途中の path を
  `verified` にせず、checker 済み edge だけで target theorem から必要命題へ
  到達できる certified subgraph を採用します。
- 証明探索は prose の上から順に進めず、Lemma Dependency Graph の frontier から
  進めます。target chain 上で certified incoming proof を持たない node を選び、
  最終命題を一歩進める最弱の局所 proposition へ縮約し、
  `verified`、`refuted`、`unprovable_under_assumptions`、
  `unverified_with_next_witness` のいずれかへ分類します。
  bare `unverified` は raw generated node や未検査生成 file の途中状態であり、
  frontier node の完了 outcome ではありません。
- 未証明 frontier node は、(a) 実装 algebra / 既存 algorithm-output projection の直接証明、
  (b) theorem variable を明示した conditional bridge 証明、
  (c) 強すぎる route の反例、
  (d) 現在の assumptions では entail しないことの witness、
  の順に試します。「難しい」だけで terminal outcome にしてはいけません。
- open frontier には、証明を進めるために必要な algorithm change を必ず書きます。
  例: 現在の recurrence / initializer / line-search / inner-solver policy を置き換える、
  acceptance rule を数学的に sound な algorithm rule として修正する、problem-class
  witness を top-level theorem assumption として明示する、theorem を
  warm-start/selected local scope に制限る、globalization / Phase-I を足す。
  これは proof guidance であり、proof-only field、diagnostic gate、runtime proof check を
  production code へ足す口実ではありません。
- `unverified_with_next_witness` を書いたらそこで止めず、named witness / next frontier を
  同じ loop へ再投入します。`verified`、`refuted`、
  `unprovable_under_assumptions`、failed Goal checklist item、または selected
  route から pruned された状態、または下位 named witness を持つ open row へ縮約するまで、
  proof note を closeout してはいけません。下位 named witness を持つ open row は
  active frontier です。
- Multi-agent Wave を使う場合、この再投入 loop を parent が実行します。各 wave の
  checked / rejected / next_witness 出力を graph overlay に integrate し、同じ
  theorem graph checker と proof search を再実行し、残った actionable frontier から
  fresh follow-up subagent を立てます。Wave は固定 fan-out ではなく、frontier が
  terminal または checked boundary に縮約されるまで続く適応的な実行単位です。
- Wave は直前の編集箇所ではなく、public-root theorem の全体 frontier board から
  開始します。frontier を returned-value projection、generated tolerance、backend
  decode、recurrence / ranking、problem / config witness などの route segment に
  グループ化し、1 回の実行単位では 1 つの route segment 全体、または同じ segment 上の
  connected frontier batch を閉じます。局所 bridge を 1 つ追加しただけで、
  同じ theorem route に進められる sibling frontier が残る場合は返答せず、board を再計算して
  次の frontier へ進みます。profile-only / obsolete branch は、選択した public theorem
  から消費されないことを graph status と edge で明示してから、次の route を選びます。
  再計算後の board で同じ route segment に actionable node が残る場合は、次の
  one-off lemma ではなく connected batch を選びます。batch は generated tolerance
  decomposition、backend decode、recurrence / ranking、public Problem / config witness
  など、同じ missing mechanism を共有する sibling node をまとめます。報告できるのは
  batch により選択行が verified、refuted、unprovable_under_assumptions、または checked
  boundary に変わった後だけです。
- board は局所 edge の一覧ではなく、目的定理レベルの分類を必ず含めます。有限停止・収束
  task では、最強の checked sufficient route、reverse / necessary 方向、循環 projection
  候補、実装 / extractor gap、algorithm-change route を別行として管理します。
  十分条件 route を閉じただけでは、必要十分条件または expressivity boundary を求める
  user target は終わりません。その場合は同じ Wave で reverse / boundary 行へ進み、
  checker-backed に証明・反証するか、closure を妨げる public input、実装、backend
  surface を直接境界として示します。local lemma の報告は、board-level milestone
  が変化した後だけ許可します。
  board は proof search の前提です。tactic 実行、bridge theorem 作成、subagent proof
  result 採用の前に、その step が閉じる board 行と route segment を特定します。
  有限停止・収束 task の board 行は、sufficient route、reverse / necessary route、
  circularity / projection-only route、実装 / extractor route、backend semantics route、
  public Problem / config expressivity route、algorithm-change route です。局所 theorem が
  選択行を閉じず、同じ行に public-root target から到達可能な sibling frontier が残る場合、
  user-facing report の前に同じ Wave で sibling batch を処理します。proof update は
  theorem 数ではなく board-level status transition を報告します。
- finite-stop / convergence target では、proof search の入口を近傍の未解決 lemma
  ではなく問題全体の board pass に固定します。board pass は final theorem、
  sufficient route、reverse / necessary route、public return projection、
  implementation / extractor route、backend route、public Problem / config
  expressivity route、algorithm-change route を列挙し、各 route の終端 leaf が
  code-derived、Problem/config-derived、backend-derived、library-derived、
  circular/projection-only、algorithmic、actionable のどれかを分類します。
  その後、一つの board 行に対する connected frontier batch を選び、行が terminal
  または checked boundary になるまで同じ batch を再投入します。単一 edge の proof は
  内部 evidence であり、同じ行の sibling edge が残る場合は成果として返しません。
- 下位 named witness が、caller lemma または target theorem edge を止めている
  関数単位の保証である場合は、それを user-facing に返してはいけません。
  同一 turn 内で callee 展開、IR / Lean 関数生成の改善、bridge proposition の変更、
  counterexample 探索、または algorithm exploration に戻し、その関数保証が
  `verified`、`refuted`、`unprovable_under_assumptions`、または現在の
  repo / tool 環境では進められない checked external boundary に到達するまで続けます。
- 下位 named witness が connection-level guarantee、すなわち code fact から
  theorem variable への binding、backend profile の instance 化、solver return から
  caller 単位への変換、または bridge lemma edge である場合も同じ扱いです。
  その接続は次の in-turn work item であり、`external_assumption` として返す前に、
  入力引数境界、production code 境界、または backend/runtime 境界まで再帰的に
  分解し、直接 frontier であることを proof-path analyzer、graph slice、または
  checker-backed model で示します。
- named witness が callee 関数を指す場合は、関数名を blocker として返さず、
  その callee の実装由来 input/output relation、return binding、loop exit 条件、
  stopping predicate、breakdown / exception predicate、nested solver / callback の返却値まで
  再帰展開します。caller 側で必要な性質が callee のどの内部 predicate から来るかを
  Lean 命題または checker-backed countermodel へ落とすまで、単なる
  "callee quality unproved" を terminal outcome にしてはいけません。
- ユーザーが「実行」「示して」「証明して」と依頼した場合、
  `unverified_with_next_witness` は同一 turn 内の作業 queue であり、
  user-facing な終端 outcome ではありません。各 frontier row は
  `verified`、`refuted`、`unprovable_under_assumptions`、または
  failed Goal checklist item へ落とすか、selected route から pruned されたことを
  checker-backed に示すか、strict に下位 named witness を持つ open row へ落とします。
  下位 witness が出た場合も直ちに同じ loop へ再投入します。
- 「どの証明 path でも証明できない」と言う場合は、絶対的な不可証明ではなく、
  現在の JIT-canonical IR、assumption ledger、生成済み backend trace coverage の
  もとで target conclusion が導けないことを、反例 model、independence result、
  または機械検査済み obligation gap で示します。失敗ログや「hard」は outcome では
  ありません。
- 関数単位の保証については、「まだ導出していない」と「保証不能」を分けます。
  proof packet が「関数 `f` は性質 `P` を保証できない」と返す場合は、
  その性質を `f` の実装由来 input/output relation 上で形式化し、現在の
  top-level assumption と code path を満たしながら `P` を否定する counterexample、
  implementation trace、または formal model を checker-backed に示します。
  さらに、その関数保証の失敗により caller-side lemma が立たず、最終 target
  theorem edge が閉じない propagation edge も証明します。これがない行は
  terminal blocker ではなく、`unverified_with_next_witness` として再帰展開します。
- 関数保証行が `guarantee_unconnected` のまま caller lemma または target theorem
  edge を止めている場合、それは user-facing な進捗ではありません。同一 turn 内の
  作業 queue として扱い、callee 展開、IR / Lean 関数生成の改善、bridge proposition の
  作り直し、反例探索、または algorithm exploration に戻します。ユーザーに返せるのは、
  その関数保証が `verified`、`refuted`、`unprovable_under_assumptions` に到達した場合、
  または現在の repository / tool 環境では進められないことを checked external boundary として
  示した場合だけです。
- user-facing に進捗を返す前に、現在選択した部品証明をすべて Goal checklist で
  処理します。部品証明ごとに `verified`、`refuted`、
  `unprovable_under_assumptions`、failed checklist item、または selected route
  から pruned された状態へ到達させます。下位
  named witness を持つ `unverified_with_next_witness` は同一 Wave の作業項目であり、
  それだけでは user-facing 進捗ではありません。単なる未検査の生成物作成、
  「未証明」の列挙だけで返してはいけません。
- target claim が `verified` / `refuted` /
  `unprovable_under_assumptions` に到達していない状態で user-facing に返す場合は、
  必ず nonterminal boundary packet を出します。これは completion ではなく、
  現在の repository / tool 環境でそれ以上進められない境界または user が明示的に求めた
  interim status です。最低限、target claim、非終端 status、通った
  checker-backed fragment、失敗した route、boundary class、boundary cause、
  必要性 status、boundary-completeness evidence、証拠 path、再開条件を示します。
  残る named witness が repository code、抽出器、generated Lean、theorem graph、
  proof overlay、local proof library、または checker output で処理可能なら、
  その witness は user-facing packet ではなく同一 Wave の work item です。
  「証明できませんでした」だけで返してはいけません。
- workflow の戻り値 contract は hard gate として扱います。
  user-facing `status=complete` は、選択された public-root Goal checklist が
  pass し、かつその theorem に到達可能な actionable frontier が theorem graph 上に
  残っていない場合だけ許可します。failed checklist item は top-level branch ではなく
  同じ Wave の work item です。user-facing `status=interim_status` は、user が明示的に
  status を求めた場合、または現在の tool / runtime / authority ではこれ以上進められない場合だけ
  許可し、completion ではないと明記して failed required items と次に自動実行する
  command を書きます。
  selected target が `open_frontier`、`unverified`、
  `unverified_with_next_witness`、`connection_unconnected`、stale generated
  evidence、local repair 可能な proof target failure、generated Lean /
  extractor / theorem-graph mismatch に到達する場合は、user-facing へ返さず、
  repair、regenerate、recheck、または次の bounded Wave を実行します。
  open frontier を持つ proof note、theorem-graph report、generated Lean file、
  Wave summary は evidence であり、workflow の戻り値ではありません。
- user-facing return の直前に exit gate を実行します。exit gate は次をすべて満たす
  必要があります。
  1. selected public-root theorem / profile が明示されている。
  2. proof status table の target-chain reachable row に bare `unverified`、
     `unverified_with_next_witness`、`connection_unconnected`、
     `guarantee_unconnected`、stale generated evidence、または local repair 可能な
     extractor / generated Lean / theorem graph mismatch が残っていない。
  3. theorem graph の leaf-origin check と forbidden-reachability check が、selected
     target から actionable frontier へ到達しないこと、または到達先が failed /
     diagnostic Goal checklist item として記録済みであることを示している。
  4. `status=interim_status` の場合、ユーザーが明示的に status を求めたか、tool /
     runtime / authority が現在の実行を止めていることを示している。
  6. theorem-critical return values が public input と implementation path から
     生成関数または uniqueness theorem で固定され、自由 witness として残っていない。
  7. 別エージェントまたは checker tool による state inspection が、この exit gate の
     入力 artifact と user-facing status を検査済みで、未反映 finding が残っていない。
  8. user target が必要十分条件、有限停止定理、または Goal 達成を求めている場合、
     sufficient route だけの verified status を `complete` に昇格していない。
  exit gate が失敗した場合は、返答せず、残った frontier を同じ Wave の work item として
  再投入します。
- user-facing に返す blocker は、選択した theorem/profile の proof graph 上で
  frontier-reduced であることを示します。すなわち、返した blocker より手前の
  target-chain node は `verified` / `refuted` /
  `unprovable_under_assumptions` / external assumption として処理済みであり、
  返した blocker の下にさらに下位の未処理 target-chain witness が残っていないことを、
  proof-path analyzer、lemma graph slice、または checker-backed boundary-completeness lemma で
  示します。高レベルな「局所収束が未証明」「KKT が未証明」だけを blocker として
  返してはいけません。
- route-specific な十分 witness、探索候補、または現在の theorem route で
  消費している変数を、数学的に必要な仮定として書いてはいけません。
  必要性は checker-backed な refutation / independence / boundary-completeness theorem が
  ある場合だけ `necessary_proven` とし、それ以外は `route_sufficient`、
  `candidate`、または `unknown` と明示します。必要性が未証明なら、命題を
  消さずに必要性主張だけを落とすのが proof-status 上の直接修正です。
- `Condition ↔ Target` が `Condition := Target` の定義展開としてだけ成立する場合、
  その route は `necessary_proven` ではなく `circularity_check` です。
  これは語彙検査ではなく graph 検査で行います。target / conclusion 側から
  proof-consumption edge を辿って、独立な `Problem` / config 条件として採用したい
  node に戻るかを確認し、戻る path があれば route-certificate evidence としてだけ扱います。
  proof graph 構造解析では、この node を採用済み target-chain 証明から外し、
  `Target` を public inputs から導くための非循環 next witness を必ず別 node として
  作ります。
- JIT-canonical evidence、theorem graph slice、proof search query packet を作ります。
- 既存 proof search を先に行い、検索 query、採用候補、除外理由を残します。
- web search は `$literature-survey` の source policy に従い、primary source、公式 docs、formal library docs、peer-reviewed paper、preprint、blog を区別します。
- Lean では、`documents/tools/lean_capability_matrix.md` を読み、frontier shape に応じて
  Lean core、Mathlib、Aesop、Plausible、LeanSearchClient、`grind`、theorem search を選びます。proof theme が明示的に
  core-only を要求しない限り Mathlib-backed route を標準とし、routine な
  propositional / constructor / relation-composition / library-lemma search obligation では
  `aesop?` / `aesop` を既定の bounded automation として試します。Nat/Int arithmetic は
  `omega` / focused `grind`、ordered linear arithmetic は `linarith`、polynomial
  recurrence は `ring_nf` / `nlinarith`、positivity/monotonicity は `positivity` /
  `gcongr` を候補にします。`exact?` / `apply?` / `rw?` / `simp?`、Mathlib docs、
  LeanSearch / Loogle / Moogle 系、Zulip archive で既存 theorem を探し、採用するのは
  checker で通った proof text だけです。強すぎる executable claim は、blocker 扱いの前に
  Plausible の counterexample route で refutation を試します。活発な proof theme では
  Mathlib/Aesop/Plausible/LeanSearchClient を topic-local Lake package に一度 pin して
  `lake build` で使えるようにし、探索用・fallback 用には
  `python3 tools/agent_tools/lean_proof_env.py all-smoke|smoke|agent-smoke|counterexample-smoke|check-file --env-dir reports/formal-proof/lean-proof-env` を使います。
  実装由来 target では、手で tactic を一つ選ぶ前に
  `lean_recursive_proof_search.py --target <name> --tactic-matrix 'exact?,apply?,simp?,aesop?,grind'`
  のような target-rooted tactic matrix を短い timeout 付きで回し、どの tactic が
  閉じるか、またはどの未解決 goal を返すかを artifact に残します。matrix の全滅は
  terminal result ではなく、返った goal を theorem graph frontier へ戻して、code fact /
  generated Lean function / Problem-config lemma / backend witness のどれが足りないかへ
  再帰分解します。`apply?` / `exact?` が `sorry` 付き partial proof や
  `Remaining subgoals` を出した場合、それは verified proof ではなく、次の
  target 候補を生成するための frontier evidence として扱います。広い target 群へ
  `aesop?` を無制限に投げてはいけません。
- Isabelle/HOL では AFP、loaded theory、Sledgehammer result、reconstruction proof を分けます。
- Coq/Rocq では library search、CoqHammer、SMTCoq、Tactician などの適用範囲と限界を記録します。
- SMT route は first-order / arithmetic / bit-vector / array など solver-friendly な obligation に限り、証明対象全体の代替にしません。
- theorem file に `<FORMAL_TARGET>`、`sorry`、`Admitted`、placeholder が残る限り `proof_status=unverified` とします。
- 証明済み claim として採用するには、target proof assistant / solver の実行 log、tool version、import context、source file path を残します。
- 証明不能 claim として採用するには、失敗ログだけでは足りません。
  `refuted` は反例、実装 trace、または formal model が target conclusion を
  否定する場合だけ使います。`unprovable_under_assumptions` は、仮定を満たして
  結論を否定する model / witness、形式体系上の独立性証明、または target theorem に
  必要な仮定が現在の assumption ledger から導けないことを示す機械検査済み
  obligation gap がある場合だけ使います。
- `blocked`、`not_run`、`unverified` は探索継続状態です。それらだけをもって
  「証明不能」と結論してはいけません。
- 導くべき補題、接続、または witness が target chain から特定済みなら、
  それを user-facing な「次の課題」として返してはいけません。同じ turn で
  生成、命題化、checker 実行、proof-status 更新まで進めます。閉じられない場合だけ、
  その witness が top-level 入力、code path、backend 境界、または
  algorithmic choice のどこで直接失敗したかを checker evidence 付きで返します。
- frontier が、実装 code shape、JIT / StableHLO / LLVM 抽出器、IR-to-Lean 生成、
  theorem graph、proof-status overlay、または proof note の不整合・不足で止まった場合、
  その finding は user-facing blocker ではなく修正対象です。詰まっている箇所を特定したら、
  直接の責務 surface を修正し、JIT / backend / Lean / theorem graph / proof-search artifact を
  再生成し、同じ public-root target theorem / theorem profile へ戻って checker を再実行します。
  修正と再実行を少なくとも一度行ってからでなければ、`unverified_with_next_witness`、
  `unprovable_under_assumptions`、または algorithmic blocker として返してはいけません。
  ただし production code に proof-only field、diagnostic gate、runtime proof check を
  追加してはいけません。修正対象は、実装アルゴリズムそのもの、抽出器、証明グラフ接続、
  既存証明文、または theorem statement の責務境界に限ります。
- 上の修正・再実行は一度だけの儀礼ではありません。repository code、抽出器、
  generated Lean、theorem graph、proof overlay、local proof library、または
  既存 checker output から次 frontier を進められる限り、Wave parent が結果を統合し、
  具体的な修正を適用または棄却し、artifact を再生成し、同じ public-root theorem に対する
  checker route を再実行します。`next_witness`、未展開の generated equation、
  missing connection、stale graph edge は、repo 内でまだ修正・再生成して試せるなら
  user-facing final answer ではありません。
- user-facing return の前に、before / after frontier board counts を route segment ごとに
  記録します。差分が小補題 1 個だけの場合は、その小補題が選択 route を閉じたか、
  ほかの sibling frontier が in-repo で進められないことを示さない限り、同じ Wave を継続します。
- checker 済み fragment を採用したら、package-retained proof trace に theorem 名、checker command、消費 fragment、残る implementation-instantiation obligation を登録します。
- implementation-derived proof trace では、証明展開や `verified` 判定の前に
  `python3 tools/agent_tools/check_proof_trace_alignment.py --trace-module <trace.py>`
  を実行し、contract の命題、retained theorem 名、source path、StableHLO anchor、
  required / forbidden source token が実装 code path と一致することを確認します。
- proof note、証明整理ノート、reader-facing proof text を作る場合は文書作成系 skill を併用します。
  - 数式が多く学術的な証明本文なら `$academic-writing` を使います。
  - 長い note / guide / workflow 形なら `$long-form-writing` を使います。
  - checker evidence や audit 結果を reader-facing にまとめる場合は `$report-writing` を使います。
- proof note には、claim ごとの証明状態対応表を必ず置きます。少なくとも
  `claim / theorem or lemma / implementation surface / proof_status / checker evidence / remaining obligation` を列として持たせます。
  `verified`、`unverified`、`not_run`、`blocked` を混ぜて prose へ埋め込まず、
  読者が一目で証明済みか否かを判定できる形にします。
- 一つの proof topic では、証明本文、仮定、未証明 gap、checker evidence を
  原則として一つの canonical proof note に統合します。実装 code path の説明は
  Design 文書に置いてよいですが、KKT や収束性の証明本文を Design 側へ分散させません。
  proof note から対応する Design 文書を明示参照し、読者が一つの proof note から
  claim、formal fragment、残課題、実装対応入口を辿れるようにします。
- checker が走らない環境では `proof_status=not_run` とし、検証 command と未確認理由を残します。

## Canonical Flow

1. Claim intake:
   - natural-language claim を一文の target に縮約する
   - Python 実装由来の claim は JIT root (`--python-symbol path.py::qualname`) から root provenance、signature、branch、return-expression obligation を抽出する
   - assumptions、definitions、notation、domain、expected theorem name を分ける
1. Algorithm expansion IR:
   - root algorithm から、initialize/config edge、solve/step/update edge、
     nested solver edge、certificate / diagnostic edge を JIT root から
     再帰展開する
   - 既定 route は
     `python3 tools/agent_tools/jit_canonical_ir.py --python-symbol <path.py::qualname> --input-factory <path.py::qualname> --out <ir.json> --stablehlo-out <root.stablehlo.mlir> --backend-trace-dir <dir> --backend-trace-out <backend.json>`
     とする。CUDA の有限精度 claim では `AGENT_CANON_JIT_JAX_PLATFORM`、
     `AGENT_CANON_JIT_BACKEND_TARGET`、
     `AGENT_CANON_JIT_IREE_CUDA_TARGET` を環境変数で固定し、
     `--xla-dump-dir <dir>` も渡して、同じ JIT root から XLA-emitted
     LLVM/PTX を収集する
   - IR node には `source_symbol`、runtime object、数学的 role、residual unit、
     dtype / backend assumption、proof relevance を持たせる
   - backend arithmetic、IREE/XLA FP32、fast-math、denormal、lowered IR などの
     実行基盤前提は、まず generated `backend_trace` と Lean の LLVM instruction
     rows に置く。証明のためだけに production `InitializeConfig` や algorithm
     state を増やしてはいけない
   - compiler/runtime semantics が proof theme の本体でない場合でも、LLVM が
     生成できる環境では外部 axiom に逃がさず、generated instruction trace と
     `lean/lib` の finite-precision model を typed witness で接続する。LLVM が
     得られない場合だけ backend coverage frontier として扱い、algorithm proof は
     その frontier が与える明示的な backend perturbation obligation を消費する
   - 実装アルゴリズムそのものは、IR から抽出した
     `trace follows A_impl / Step_impl` という operational assumption として置く。
     convergence、finite termination、residual reachability、certificate
     soundness は、この operational assumption から導く lemma / theorem であり、
     assumption にしてはいけない
   - proof status overlay では operational assumption を
     `operational_assumptions` に置く。未証明数理 gap の `open_frontier`、
     backend / runtime boundary の `external_assumptions`、反例付きの
     `unprovable_under_assumptions` と混ぜない
   - IR edge には `calls`、`initializes`、`updates_state`、`requests_certificate`、
     `projects_status`、`performance_only` などの関係を持たせる

- final target theorem から backward slice し、必要な局所 proof obligation と
  不要な implementation detail を分ける。Pyright や型構造でわかる事実は、
  最終命題の数学的依存でない限り証明対象にしない
- 初期化・cold-start・Phase-I 由来の事実は、proof route の blocker として
  返す前に IR `code_facts` から具体式を拾い、lemma graph 上の
  initialization / selected-scope-entry node に接続する。コードから直接わかる式を
  `unverified_with_next_witness` や user-facing blocker に残さない
- selected initializer は `Init(Problem, InitializeConfig)` として扱い、
  hard-coded zero、default vector、supplied state などの個別値は IR が示す
  実装特殊化としてだけ使う

1. Lemma dependency graph:
   - JIT-canonical IR JSON を
     theorem graph generator へ渡し、補助命題 graph を生成する
   - graph は現行 JIT-canonical IR から再生成する。旧graphとの同期は
     fingerprint ではなく、graph connectivity、implementation token、
     `code_derived_facts` と IR/lemma graph の対応で検査する
   - lemma node は auxiliary lemma、assumption、target theorem/profile を表す
   - lemma edge は「source lemma が target lemma を消費する」依存を表す
   - lemma id は implementation symbol ではなく IR `node_id` から作る。
     複数の algorithm / solver が同じ `_solve` などの symbol 名を持てるため、
     symbol 名だけで lemma を同一視しない
   - 一つの algorithm に対して `all`、`certificate_soundness`、
     `local_convergence`、`fp32_floor`、`solver_chain` など複数の target/profile
     node を持たせ、proof note は対象 theorem の target chain を明示してから
     本文へ進む
   - graph validation で edge endpoint、cycle absence、target chain reachability を
     機械検査する。validation fail の graph から `verified` claim を作らない
1. Proof path exploration:
   - 証明 path は固定手順ではなく、agent / human が Try and Error で探索する
     editable graph overlay として扱う
   - IR-backed obligation node は source IR から再生成される正本なので、
     手作業で削除 / rename / 意味変更しない。source program が変わった場合だけ
     IR を再生成して同期する。証明 path の探索で不要に見える node は、
     graph から消さず、対象 target chain / certified subgraph / missing frontier の
     採否で扱う
   - agent / human は auxiliary lemma、bridge lemma、dependency edge、
     proof attempt、failed route、existing-proof candidate、literature evidence、
     checker command を graph overlay に追加できる
   - 各 attempt は `target_lemma`、`method`、`input_evidence`、`checker_status`、
     `result_status`、`adoption_decision`、`next_frontier` を持つ
   - `result_status=unverified_with_next_witness` の attempt は、`next_frontier` を
     次の探索対象として即座に再投入する。bare `unverified` は unchecked generated file や
     未実行 node の状態に限り、frontier の最終分類には使わない
   - `next_frontier` が repository code、既存 proof library、公式 source packet、
     local run artifact、または checker output から導出可能なら、ユーザーへ
     「未証明」と返す前に、その証拠捕捉・IR/lemma graph overlay・proof note
     更新・必要な bounded code 修正を実装する。返答してよいのは、証拠が
     user-owned external run、未導入 tool、権限、または proof theme 外の外部
     semantics に依存する場合だけです。その場合も named witness を終端にせず、
     failed / diagnostic Goal checklist item として分類する
   - proof note は探索 log 全体ではなく、現在採用する certified subgraph と
     missing frontier を示す。`verified` と言えるのは checker 済み theorem /
     lemma と、それらだけで接続された target chain に限る
1. Evidence generation:
   - 実装正本に合う selected route から generated Lean evidence を生成する。
     JIT route では StableHLO、backend trace、JIT IR、generated Lean evidence、
     C++ source route では `cpp_template_to_lean.py` で source envelope、
     source facts、thin operational IR、generated Lean evidence を生成する
   - output は run bundle、report、または project-local proof artifact directory に置く
   - reader-facing proof text は topic ごとに一つの canonical proof note へ統合し、
     theorem statement、assumption ledger、checked fragment status、remaining gap を
     別文書へ分散させない。implementation code path の説明は Design 文書へ置き、
     proof note から明示リンクする。
   - proof note の冒頭または theorem section 直後に、証明状態対応表を置く。
     対応表は、checked fragment と未証明 obligation を同じ表で扱い、
     `verified` の claim だけでなく、`unverified` の理由と次に必要な
     implementation-instantiation obligation も明示する。
1. Existing proof search:
   - local repo、`references/`、`notes/`、`documents/` を先に確認する
   - formal library docs と theorem search tools を確認する
   - web search / paper search は `$literature-survey` として source packet に残す
1. Formalization:
   - target proof assistant を選ぶ
   - `<FORMAL_TARGET>` を正式な proposition に置き換える
   - informal proof sketch を assistant-checkable lemmas に分ける
1. Automation:
   - Lean では Mathlib/Aesop/Plausible/LeanSearchClient を標準 automation / theorem-search / counterexample route とし、`aesop?` / `aesop`、Lean/mathlib tactic search、Plausible counterexample probes、Isabelle Sledgehammer、CoqHammer、SMT solver などを bounded subgoal に使う
   - automation result は再構成・境界化・checker log まで確認する
1. Verification:
   - generated command か project-specific command を実行する
   - log が pass した file / theorem だけを verified にする
   - placeholder、admit、sorry は gap として残す。backend semantics は
     external axiom として採用せず、生成 backend trace の coverage gap として
     記録する
   - proof search が失敗した場合は、失敗を terminal result にしない。
     theorem が偽である反例、仮定不足 witness、形式的 independence、
     または実装 path と theorem の矛盾を証明できる場合だけ
     `refuted` / `unprovable_under_assumptions` として採用する
   - verified fragment は package-retained trace に反映し、実装 code path、
     residual unit、stopping guard、backend arithmetic、final-status projection など
     未 instantiate の bridge を proof boundary として残す
   - 実装 code path の説明が proof claim を理解するために必要な場合は、Design 文書に
     対応表または code-path 節を置き、proof note から参照する。証明本文、仮定、
     theorem target、gap ledger は proof note 側を正本にし、Design 側へ重複させない。
   - 最上位 theorem statement は
     `ImplementedTrace -> ProblemWitnesses -> BackendWitnesses -> Convergence`
     の形に正規化する。`ImplementedTrace` は仮定、`Convergence` は導出補題であり、
     `Convergence` 自体を仮定に入れない
1. Handoff:
   - 学術文章へ戻す場合は `$academic-writing` / `$paper-writing`
   - proof note や長い証明整理文書へ戻す場合は `$academic-writing` または
     `$long-form-writing`
   - 文献・既存 proof の source trail は `$literature-survey`
   - reader-facing report は `$report-writing`

## Required Outputs

```text
proof_claim=<path-or-inline-summary>
proof_jit_ir=<path>
proof_stablehlo=<path>
proof_generated_lean=<path>
proof_theorem_graph=<path-or-section-anchor>
proof_library_trace_module=<path>
proof_checker_command=<command>
proof_checker_log=<path|not_run>
proof_status=<verified|refuted|unprovable_under_assumptions|unverified_with_next_witness|unverified|not_run|blocked>
proof_terminal_outcome=<verified|refuted|unprovable_under_assumptions|none>
proof_impossibility_certificate=<path-or-section-anchor|none>
proof_source_packet=<path>
proof_source_kind=<natural_language|jit_canonical_root|theorem_graph>
proof_algorithm_ir=<path-or-section-anchor|none>
proof_goal_directed_slice=<path-or-section-anchor|none>
proof_selected_local_obligations=<path-or-section-anchor|none>
proof_lemma_graph=<path-or-section-anchor|none>
proof_target_chains=<path-or-section-anchor|none>
proof_lemma_graph_validation=<pass|fail|not_run>
proof_lemma_graph_overlay=<path-or-section-anchor|none>
proof_path_attempts=<path-or-section-anchor|none>
proof_certified_subgraph=<path-or-section-anchor|none>
proof_missing_frontier=<path-or-section-anchor|none>
proof_status_table=<path-or-section-anchor>
proof_forbidden_reachability_check=<command-and-log|not_run>
goal_checklist=<path-or-section-anchor>
proof_unconnected_frontier_check=<pass|fail>
proof_actionable_frontier=<none|path-or-section-anchor>
proof_user_return_status=<complete|boundary_reached|interim_status|not_allowed>
proof_initialize_root=<module.initialize|none>
proof_initialize_expansion_graph=<path-or-section-anchor|none>
proof_trace_alignment_check=<command-and-log|not_run>
proof_nonterminal_return=<path-or-section-anchor|none>
```

`proof_user_return_status=not_allowed` is not user-facing output. It means the
agent must keep working in the same Wave: repair, regenerate, recheck, or reduce
the frontier to a checked boundary before responding. `proof_actionable_frontier`
must be `none` for `complete`; for `boundary_reached` it must point only to the
checked direct boundary, not to an unconnected helper theorem.

## Proof Status Table

Reader-facing proof notes must include a table shaped like this:

| Claim     | Formal theorem / lemma | Implementation surface | Status                                                                                                                          | Evidence                               | Remaining obligation |
| --------- | ---------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | -------------------- |
| `<claim>` | `<theorem>`            | `<path::symbol>`       | `verified` / `refuted` / `unprovable_under_assumptions` / `unverified_with_next_witness` / `unverified` / `not_run` / `blocked` | `<checker command/log/counterexample>` | `<gap or none>`      |

Use `verified` only for checker-passing artifacts without proof escape hatches.
Use `refuted` only when a counterexample, formal model, or implementation trace
falsifies the target conclusion. Use `unprovable_under_assumptions` only when
there is a checked independence result or a model / witness showing that the
current assumptions do not entail the target claim.
For implementation-derived claims, a helper-level, component-level,
residual-slice, or otherwise partial counterexample is not a user-facing
`refuted` result until it is embedded into the top-level public theorem trace.
Before returning or adopting that counterexample, prove a
reachability/instantiation theorem from the current top-level `Problem` /
config / backend assumptions and JIT-canonical `main` or run path to the local
state, input, model, or trace used by the counterexample, and prove the
propagation edge from the local falsified property to the target theorem
conclusion. If either edge is missing, classify the artifact as
`local_counterexample_candidate` or `route_rejected_not_top_level_reachable`,
keep it in the failed-route overlay, and continue the target-rooted frontier
search. Do not report it as terminal refutation or unprovability.
Use `unverified` for prose claims, conditional sketches, assumptions, or
implementation-instantiation obligations that have not been discharged. Use
`not_run` when the checker was unavailable, and `blocked` when a missing
definition, library, or implementation fact prevents progress.
For frontier rows in a proof note, prefer `unverified_with_next_witness` over
bare `unverified`, and fill the remaining-obligation cell with the named
theorem variable, existing algorithm-output projection, backend evidence, problem-class witness,
or theorem restriction needed next. A bare `unverified` frontier row is not a
closeout state.
For implementation-derived proof tasks, `Remaining obligation` is an internal
frontier cell, not a user-facing final answer. A row with a named theorem
variable, projection, backend evidence, or problem-class witness must either be
re-entered in the same Wave or represented as a failed / diagnostic Goal
checklist item showing the exact code / input / backend / algorithm boundary
that prevents local progress. Otherwise the proof note is still an active work
item.
Rows whose remaining obligation is an unconnected theorem graph edge, missing
generated Lean value, generated equation not consumed by the proof graph, or
callee guarantee not expanded are never final rows. They must be expanded,
repaired, regenerated, or reduced to a checked boundary before the skill can
return.
For individual proof rows, `verified`, `refuted`, and
`unprovable_under_assumptions` remain checker statuses. They are not top-level
branches for an implementation-derived Goal. The Goal is closed only when all
required checklist items for the public-root theorem pass. If a row does not
close the Goal, add or update the corresponding check item and keep the same
Wave running unless the user explicitly asked for an interim status.

## Nonterminal Proof Return

When the target theorem is not closed, a user-facing interim return is allowed
only when the user explicitly asks for status. It is not a completion state.
For implementation-derived proof tasks, the packet must explain which required
Goal checklist items failed and which code path / generated definition /
theorem graph edge they correspond to; it must not be a list of missing helper
lemmas. Use this shape:

| Field                       | Required Content                                                                                                                                         |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target claim                | Exact theorem or natural-language claim being attempted                                                                                                  |
| Current nonterminal status  | `boundary_reached`, `user_input_required`, `external_tool_unavailable`, or `interim_status`; do not call it terminal                                     |
| Strongest checked fragments | Theorems / artifacts that passed, with checker command                                                                                                   |
| Failed or rejected routes   | The route, why it does not close the target, and whether it is refuted, too strong, unreachable from the public root, or incomplete                      |
| Boundary class              | `code_shape`, `extractor`, `generated_lean`, `theorem_graph_wiring`, `problem_config_input`, `backend_runtime`, `formal_library`, or `algorithm_choice` |
| Boundary cause              | The exact production mechanism, public input condition, backend/runtime surface, tool absence, or algorithmic choice that blocks the target theorem      |
| Necessity status            | `necessary_proven`, `route_sufficient`, `candidate`, `unknown`, or `algorithmic_blocker_proven`; do not imply necessity from a selected proof route      |
| Boundary evidence         | Target-chain/frontier evidence showing no lower-level actionable blocker remains under this returned row                                                     |
| Evidence path               | Proof status row, lemma graph node, Lean file, source packet, log, or code path                                                                          |
| Resume condition            | Exact local change, external evidence, user-owned input, tool availability, or theorem restriction needed before the same target can continue              |

If the result is `unprovable_under_assumptions`, include the witness/model that
satisfies the assumptions while falsifying the entailment. If the result is
`refuted`, include the counterexample, formal model, or implementation trace
that falsifies the target conclusion. If the result is nonterminal, state why
local recursion, IR / graph regeneration, proof search, and algorithm
exploration cannot currently advance it. A selected route may be a useful
sufficient condition without being necessary; mark that distinction explicitly.
If a returned boundary cannot be shown frontier-reduced, do not return it.
Decompose it once more, repair the graph/extractor when possible, or state the
tool/checker limitation that prevents the boundary-completeness check.

Forbidden implementation-derived return:

- "Need theorem `ReturnedKKTVectorResidualDrop`." This names a missing theorem
  without showing why the current code path cannot provide it.

Accepted boundary return:

- `Boundary class=generated_lean`: generated Lean leaves
  `python/solver.py::solve_direction` return vector unconstrained; the public
  root theorem consumes that vector in the residual-decrease edge; extractor
  coverage and forbidden-reachability checks show no lower-level code-derived
  equation is available. Resume by repairing that extractor edge and rerunning
  the same public-root theorem.

## JIT-canonical IR

実装由来のアルゴリズム証明では、証明本文を書く前にアルゴリズムを
機械的に再帰展開し、中間表現として保持します。これは最終命題から見た
必要十分な局所証明を選ぶための構造であり、IR 自体を `verified` claim には
しません。

1. root は `initialize`、`solve`、`step`、または対象 theorem が消費する
   public algorithm entrypoint から選びます。
1. JIT root、`InitializeConfig` ownership、nested solver selection、
   state update、certificate projection、diagnostic construction を node / edge として
   展開します。対象 module を import / execute してはいけません。
   import 先を展開するときも runtime import は使わず、`--root`、慣用的な
   `python/` / `src/`、または明示 `--import-root` にある source file を JIT lower
   します。同一 repository に限定せず、source tree が明示されていれば外部 repo /
   vendored source も同じ規則で扱います。
1. 各 node を `mathematical_state_transition`、`linear_or_nonlinear_solve`,
   `certificate`, `stopping_predicate`, `diagnostic`, `performance_only`,
   `implementation_bookkeeping` のように分類します。
1. final theorem から backward slice し、必要な局所定理、仮定、未証明 gap だけを
   selected local obligations に残します。最終命題へ到達しない helper、
   型検査で足りる構造、実行時 convenience field は証明対象から外します。
   instance method dispatch や constructor binding は証明本文へ入れず、
   `static_checks` として proof selection 前に落とします。dispatch edge は
   obligation の `consumes_edges` に入れず、callee の数学的 theorem だけを
   node / child proof scope として残します。
   callback argument と callable algorithm field も同じです。
   例: `while_loop(..., stepper.step, ...)` は `stepper.step` の static callback
   binding を落とし、`runtime.solver_algorithm(...)` は field annotation から
   選ばれた lower solver theorem だけを残します。
   `self.update(...)` のような function-pointer variant は、同一 JIT-lowered module に
   見える variant function 群へ保守的に展開し、variant selection は static
   dispatch check、各 variant の数学的内容は個別 node として扱います。
1. slice 後に残った各 obligation を、formal theorem、existing proof search、
   literature evidence、または problem-class / backend assumption のいずれかへ
   割り当てます。

JIT-canonical IR record は次の形を基本にします。

| Field                 | Meaning                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `ir_node_id`          | stable node identifier                                                                           |
| `source_symbol`       | `path.py::qualname` or theorem/source anchor                                                     |
| `runtime_object`      | `Problem`, `State`, `SolveConfig`, `Info`, residual block, direction, etc.                       |
| `math_role`           | state transition, residual map, direction solve, certificate, or bookkeeping                     |
| `edge_kind`           | call, initialize, state update, certificate request, status projection, or performance-only edge |
| `residual_unit`       | residual or norm unit if the node exports numeric evidence                                       |
| `precision_model`     | dtype/backend floor or `none`                                                                    |
| `backend_assumptions` | proof-only backend profile variables and witness obligations                                     |
| `proof_relevance`     | required, assumption, helper, performance-only, or excluded                                      |
| `selected_obligation` | local theorem / lemma required by the final target, or `none`                                    |

Static check record は、証明前に機械的に片付く構造制約を表します。

| Field          | Meaning                                                                     |
| -------------- | --------------------------------------------------------------------------- |
| `check_kind`   | constructor resolution or instance method resolution                        |
| `edge_id`      | expansion edge discharged before proof selection                            |
| `status`       | `statically_checked`, `static_checker_required`, or `static_resolution_gap` |
| `proof_effect` | why this edge is removed from proof obligations                             |

## Lemma Dependency Graph

JIT-canonical IR から補助命題を作る段階では、命題を graph として
保持します。一つの algorithm は複数の theorem target を持てるため、補助命題を
一つの線形 list や単一 heading のみで管理してはいけません。

1. JIT-canonical IR JSON から lemma graph を生成します。
   graph node は auxiliary lemma、assumption、target theorem/profile を表し、
   graph edge は「source lemma が target lemma を消費する」依存を表します。
   生成物は初期 graph であり、証明探索では agent / human が overlay として
   補助命題、bridge lemma、dependency edge、proof attempt を追加します。
1. lemma id は IR `node_id` 由来にします。複数の algorithm / solver が
   同じ `_solve` などの symbol を持てるため、symbol 名だけで lemma を
   同一視してはいけません。
1. target/profile node は `all`、`certificate_soundness`、
   `local_convergence`、`fp32_floor`、`solver_chain` のように分けます。
   proof note は証明したい theorem/profile の target chain を引用してから
   証明本文に入ります。
1. graph validation は edge endpoint、cycle absence、target chain reachability を
   機械検査します。validation fail の graph から `verified` claim を作っては
   いけません。
1. IR-backed obligation node は source IR の再生成で管理します。agent / human が
   直接編集してよいのは overlay 側の auxiliary lemma、bridge lemma、
   dependency edge、proof attempt、adoption decision、missing frontier です。
   IR-backed node の削除、rename、意味変更は source program の変更に伴う
   IR 再生成でだけ行います。証明探索で不要に見える IR-backed node は
   graph から消さず、対象 target chain、certified subgraph、missing frontier の
   採否で扱います。
1. Proof path は探索対象です。失敗 path も `failed` / `blocked` attempt として
   残し、次の frontier を graph から選びます。ただし reader-facing proof claim に
   採用できるのは、`verified` theorem / lemma と checker evidence を持つ edge だけで
   target theorem へ接続された certified subgraph です。
1. static dispatch、import binding、callback binding、function-pointer variant は
   dependency edge として graph に現れてよいですが、それ自体を数学 lemma として
   証明本文に混ぜません。選ばれた callee / variant の theorem node だけが
   数学的内容を持ちます。

## Frontier Exploration Loop

graph 生成後、algorithm theorem を進めるときは次の loop を回します。

1. target theorem / profile を一つ選び、その target chain 上の uncertified frontier を
   graph から機械的に取り出します。複数 downstream edge を解放する node を優先しますが、
   明らかに強すぎる claim は先に反例で潰してよいです。
1. frontier node を次の四種類へ正規化します。
   - exact implementation identity: 実装の式変形、projection、reconstruction
   - conditional bridge: 下位 theorem / certificate があれば上位 theorem へ渡せる命題
   - reachability / existence: 反復法が tolerance に届く、line search が受理する、など
   - algorithmic-blocker analysis: 現在の algorithm choice が theorem を
     阻んでいるか、その choice を変えるとどの proof obligation が必要になるか
   - external assumption binding: backend profile、problem-class、selected local scope witness
1. 正規化した命題に対して checker-backed な結果を一つ取りに行きます。
   - `verified`: escape hatch なしで checker が命題を証明した
   - `refuted`: counterexample / formal model / implementation trace が命題を否定した
   - `unprovable_under_assumptions`: 現在の assumptions を満たす witness が結論を否定し、
     assumption ledger からは命題が導けないことを示した
   - `unverified_with_next_witness`: 必要な theorem variable、existing algorithm-output projection、
     backend evidence、problem-class witness が特定されている
     この場合は named witness / next frontier を同じ loop へ即座に再投入し、
     bare `unverified` のまま proof note を closeout しない
1. 単独の補題候補が強すぎて失敗しても、その downstream theorem が失敗したとは
   扱いません。失敗した route は overlay に残し、より弱い補題、隣接 graph fact、
   code-derived identity、problem witness を束ねた certified subgraph で同じ
   downstream node を閉じられるかを探索します。target theorem の否定や
   `unprovable_under_assumptions` は、そのような合成 route でも閉じないことを
   checker-backed に示した場合だけ採用します。
1. 弱い命題だけが証明できた場合は、その弱い命題から target theorem へ何が不足するかを
   bridge edge として残します。強い route が refuted の場合は、refutation を残し、
   theorem restriction または algorithm change を書きます。
1. blocker が algorithmic choice にある場合は、変更候補を proof obligation として
   書き出し、実装変更後に IR / lemma graph を再生成して同じ loop へ戻します。
   algorithm-change guidance だけで target theorem の作業を終えません。
1. proof status table と proof note を同じ pass で更新します。open row は active
   frontier であり、次が数学証明、implementation return-value projection、
   backend evidence binding、theorem restriction のどれかを必ず示します。user-facing
   に返せる途中状態は、その row が failed / diagnostic Goal checklist item として
   記録されている場合だけです。

Proof path attempt record は次の形を基本にします。

| Field               | Meaning                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `attempt_id`        | stable attempt identifier                                                                   |
| `target_lemma`      | lemma or theorem node the attempt tries to discharge                                        |
| `method`            | proof assistant, existing-proof search, hand proof, SMT, numeric bound, or literature route |
| `input_evidence`    | source theorem, paper, code anchor, checker file, or calculation used                       |
| `checker_status`    | `pass`, `fail`, `not_run`, or `not_applicable`                                              |
| `result_status`     | `verified`, `failed`, `blocked`, `assumed`, or `candidate`                                  |
| `adoption_decision` | `adopted`, `rejected`, `superseded`, or `deferred`                                          |
| `next_frontier`     | lemma nodes or assumptions still needed after this attempt                                  |

## Initialize-Rooted Proof Expansion

アルゴリズム module が `initialize(config: InitializeConfig)` で下位 solver、
stopping predicate、preconditioner などを再帰的に初期化する場合は、
JIT-canonical IR の一部として `InitializeConfig` ownership edge を
展開します。ただし `initialize` 自体を数学的証明の前提にしません。
証明本体は solver / optimizer / stopping / preconditioner ごとの独立 theorem として
保持し、`initialize` はどの独立 proof scope が必要かを列挙する dispatch surface に
限定します。

1. `root_initialize` と `root_config_type` を明記します。
   例: root optimizer の `initialize` + `InitializeConfig`、
   standalone solver ならその solver の `initialize` + `InitializeConfig`。
1. `InitializeConfig` の子 field ごとに expansion edge を書きます。
   edge は少なくとも `child_config_field`、`child_initialize`、
   `proof_scope`、`selection_rule`、`role` を持たせます。
   例: root optimizer config の child solver field -> child solver `initialize`、
   child solver config の inner solver field -> inner solver `initialize`。
1. method や algorithm family が変わる surface では、caller theorem を
   書き換えず、method registry / variant registry で別 proof scope を選びます。
   下位証明は method ごとに独立させ、caller は選択された scope の certificate を
   top-level substitution lemma に渡します。
1. standalone 利用では、その module の `initialize` を root にします。
   たとえば standalone iterative solver の証明展開はその solver の `initialize` から始め、
   caller optimizer や unrelated block solver の proof scope を含めません。
1. preconditioner と stopping predicate も child scope として展開できますが、
   役割を混ぜません。physical true residual を返す solver では、
   preconditioner quality は requested residual へ到達する reachability proof に置き、
   返却 residual budget の追加項にしません。
1. expansion graph と proof dependency graph は分けます。
   expansion graph の edge は runtime ownership / initialization ownership を表し、
   proof dependency graph の edge は theorem / lemma consumption を表します。
   両者を混ぜて `verified` claim を作ってはいけません。
1. proof-only config や proof-only state は追加しません。
   実行時に存在する `InitializeConfig`、`SolveConfig`、`Problem`、`State`、`Info`
   だけを source surface とし、証明でしか使わない量は theorem 変数または
   problem-class / backend assumption として残します。

Expansion graph record は次の形を基本にします。

| Field                | Meaning                                                                                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `root_initialize`    | root module initialize function                                                                                                                                                 |
| `root_config_type`   | root `InitializeConfig` type                                                                                                                                                    |
| `proof_scope`        | independent theorem family required at that root                                                                                                                                |
| `child_config_field` | field that owns a nested `InitializeConfig`                                                                                                                                     |
| `child_initialize`   | nested initialize function selected by that field                                                                                                                               |
| `selection_rule`     | static field, variant tag, or method registry rule selecting the child                                                                                                          |
| `role`               | correctness certificate, reachability certificate, stopping predicate, or performance-only helper                                                                               |
| `status`             | `verified`, `refuted`, `unprovable_under_assumptions`, `unverified_with_next_witness`, `unverified`, `not_run`, or `blocked` for the proof scope, not for initialization itself |

## Nested Iterative Solver Proofs

外側アルゴリズムが内側の反復法に依存する場合は、反復の証明を
外側 claim へ直結させず、要求精度を上から下へ渡す形にします。

1. 外側 iteration の添字をすべての量に付けます。条件数、スケーリング、
   必要精度、前処理誤差を固定定数に潰してはいけません。固定定数を使う場合は、
   selected local scope 全体で一様 bound が成り立つことを別 theorem として証明します。
1. まず外側 recurrence が必要とする方向誤差や residual floor を決め、そこから
   inner solver の requested residual budget を導出します。典型形は
   `effective_residual_budget_k <= requested_residual_budget_k` なら
   `direction_error_k <= requested_direction_error_k` です。
1. reduced KKT では、動的 gain を少なくとも
   `reduced_inverse_gain_k`、`backsubstitution_gain_k`、
   scaling / floor-model gap、backend arithmetic floor に分けます。
1. proof obligation は依存順にネストします。外側 recurrence request、
   reduced-system residual request、Krylov solver true-residual certificate、
   preconditioner spectral / norm-conversion certificate、backend residual
   reconstruction floor の順に並べます。
1. 下位 solver lemma は、利用側でしか決まらない量を変数のまま展開します。
   動的 gain、requested residual budget、selected tolerance、
   problem/current-state regularity witness は、下位証明内で計算せず、
   利用側の top-level substitution lemma で代入します。
1. 前処理は外側証明の shortcut ではなく、内側 solver certificate の一部です。
   preconditioned residual を使う場合は、外側 residual 単位へ戻す norm-conversion
   bound を証明してから使用します。
   実装が physical true residual を再計算して返す場合、前処理精度はその residual
   へ到達する reachability proof に置き、返却 residual budget の追加項にしません。
1. 実行事実だけを既存の algorithm `Info` や diagnostics surface に出します。
   proof-only config や proof-only state を追加して obligation を満たしてはいけません。
1. 未解決事項は `local_reduced_kkt_inverse_gain_k`、
   `backsubstitution_gain_k`、
   `preconditioned_to_physical_residual_gain_k`、
   `fp32_backend_floor_k` のように、単位と所属を明示した problem-class /
   backend assumption として記録します。

## Target Selection

- Default to Lean 4 for ordinary mathematical formalization when no project
  policy or existing artifact selects another prover.
- Use Isabelle/HOL when the claim depends on Isabelle libraries, AFP material,
  or Sledgehammer reconstruction is a good fit.
- Use Coq/Rocq when the project already owns Coq artifacts, dependent program
  proofs, extraction, or Coq-specific libraries.
- Use SMT only for subgoals that fit solver theories or as a certificate
  route, not as a replacement for higher-order or library-heavy mathematics.

## Proof Status Boundary

`verified` is allowed only when a checker command succeeds on the exact formal
artifact and the artifact has no placeholders or unchecked proof escape hatches.
Everything else is planning, search evidence, or an unverified proof sketch.
