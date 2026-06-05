# formal-proof-workflow
<!--
@dependency-start
responsibility Documents the natural-language to formal-proof workflow.
upstream design ../canonical/skills.md skill canon registry.
upstream design literature-survey.md source search and bibliography workflow.
upstream design research-workflow.md external research and implementation loop.
upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffolds.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant references.
downstream implementation ../../.agents/skills/formal-proof-workflow/SKILL.md exposes the skill to Codex.
@dependency-end
-->

## Purpose

自然言語の数学的主張、証明スケッチ、設計上の lemma、または
Python AST から抽出した証明候補を、形式証明へ進めるための workflow です。
この skill は、claim を assumptions / definitions / theorem target /
proof obligations / existing proof search / checker command に分解します。
最終目的は、target claim を checker-backed に証明するか、同じ claim が
現在の仮定・実装経路からは証明できないことを反例、独立性、または
仮定不足 witness によって示すことです。
LLM 生成文、自然言語証明、未実行の theorem stub を証明済みとは扱いません。
`blocked`、`not_run`、`unverified` は途中状態であり、skill の完了判定では
ありません。

## Use When

- 文書や設計にある数学的 claim を Lean、Isabelle/HOL、Coq/Rocq、SMT などへ形式化したい
- 既存 formal library に theorem や lemma があるかを先に探したい
- proof assistant を使う前に proof obligation、前提、定義不足を棚卸ししたい
- 論文、scholarly note、optimization / numerical method design の理論 claim を検査可能な形に落としたい
- Python 実装の特定 symbol から side-effect-free な AST 抽出で proof scaffold を作りたい

## Core References

- `agents/skills/literature-survey.md`
- `agents/skills/academic-writing.md`
- `agents/skills/long-form-writing.md`
- `agents/skills/report-writing.md`
- `agents/skills/research-workflow.md`
- `agents/skills/paper-writing.md`
- `documents/tools/formal_proof.md`
- `references/agent-canon-technology-bibliography.md`

## Mandatory Checklist

- 形式化前に、claim、assumptions、definitions、target theorem、proof sketch を分けます。
- 実装由来の claim は `formal_proof.py --python-symbol path.py::qualname` で
  AST から抽出できます。この route は対象 module を import / execute しません。
- アルゴリズム由来の claim では、局所証明を選ぶ前に root algorithm を
  AST / initialize edge / call edge から機械的に再帰展開し、
  Algorithm Expansion IR として保持します。IR は proof ではなく、
  最終命題に必要な局所 theorem / lemma だけを選ぶための中間表現です。
- Algorithm Expansion IR は `python3 tools/agent_tools/algorithm_expansion_ir.py`
  で作成し、`proof_algorithm_ir`、`proof_goal_directed_slice`、
  `proof_selected_local_obligations` として proof note または run artifact に残します。
- backend / dtype / IREE / finite-precision semantics は production code や
  `InitializeConfig` へ proof-only field として足さず、Algorithm Expansion IR の
  `backend_assumptions` と Lemma Dependency Graph overlay に theorem variable /
  witness obligation として保持します。
- checker 向け中間表現、lemma graph、profile library、Lean stub は
  `lean/<proof-theme>/` に置き、再利用する profile / arithmetic library は
  `lean/lib/` に置きます。profile library を読むのは
  `algorithm_expansion_ir.py` などの証明ツールであり、production algorithm は
  読みません。reader-facing な証明本文は `notes/themes/` を正本にし、`lean/` には
  機械可読 artifact と checker artifact を置きます。
- Algorithm Expansion IR から `python3 tools/agent_tools/algorithm_lemma_graph.py`
  で Lemma Dependency Graph を作成し、`proof_lemma_graph`、
  `proof_target_chains`、graph validation evidence として proof note または
  run artifact に残します。IR は実装展開、lemma graph は命題依存を表し、
  両者を混ぜて `verified` claim を作ってはいけません。
- Lemma Dependency Graph は証明探索の編集対象です。機械生成された
  IR-backed obligation は source program の変更に伴う IR 再生成でだけ同期し、
  agent / human が追加する
  補助命題、dependency edge、proof attempt、採用 / 棄却理由は
  graph overlay として provenance 付きで残します。探索途中の path を
  `verified` にせず、checker 済み edge だけで target theorem から必要命題へ
  到達できる certified subgraph を採用します。
- `python3 tools/agent_tools/formal_proof.py` で scaffold と query packet を作ります。
- 既存 proof search を先に行い、検索 query、採用候補、除外理由を残します。
- web search は `$literature-survey` の source policy に従い、primary source、公式 docs、formal library docs、peer-reviewed paper、preprint、blog を区別します。
- Lean/mathlib では mathlib docs、LeanSearch / Loogle / Moogle 系、Zulip archive、`exact?` / `apply?` のような in-editor tactic search を候補にします。
- Isabelle/HOL では AFP、loaded theory、Sledgehammer result、reconstruction proof を分けます。
- Coq/Rocq では library search、CoqHammer、SMTCoq、Tactician などの適用範囲と限界を記録します。
- SMT route は first-order / arithmetic / bit-vector / array など solver-friendly な obligation に限り、証明対象全体の代替にしません。
- theorem stub に `<FORMAL_TARGET>`、`sorry`、`Admitted`、placeholder が残る限り `proof_status=unverified` とします。
- 証明済み claim として採用するには、target proof assistant / solver の実行 log、tool version、import context、source file path を残します。
- 証明不能 claim として採用するには、失敗ログだけでは足りません。
  `refuted` は反例、実装 trace、または formal model が target conclusion を
  否定する場合だけ使います。`unprovable_under_assumptions` は、仮定を満たして
  結論を否定する model / witness、形式体系上の独立性証明、または target theorem に
  必要な仮定が現在の assumption ledger から導けないことを示す機械検査済み
  obligation gap がある場合だけ使います。
- `blocked`、`not_run`、`unverified` は探索継続状態です。それらだけをもって
  「証明不能」と結論してはいけません。
- checker 済み fragment を採用したら、package-retained proof trace に theorem 名、checker command、消費 fragment、残る implementation-instantiation obligation を登録します。
- implementation-derived proof trace では、証明展開や `verified` 判定の前に
  `python3 tools/agent_tools/check_proof_trace_alignment.py --trace-module <trace.py>`
  を実行し、contract の命題、retained theorem 名、source path、AST anchor、
  required / forbidden source token が実装 code path と一致することを確認します。
- proof note、証明整理ノート、reader-facing proof text を作る場合は文書作成系 skill を併用します。
  - 数式が多く学術的な証明本文なら `$academic-writing` を使います。
  - 長い note / guide / workflow 形なら `$long-form-writing` を使います。
  - checker evidence や audit 結果を reader-facing にまとめる場合は `$report-writing` を使います。
- proof note には、claim ごとの証明状態対応表を必ず置きます。少なくとも
  `claim / theorem or lemma / implementation surface / proof_status /
  checker evidence / remaining obligation` を列として持たせます。
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
   - Python 実装由来の claim は AST source (`--python-symbol path.py::qualname`) から root provenance、signature、branch、return-expression obligation を抽出する
   - assumptions、definitions、notation、domain、expected theorem name を分ける
1. Algorithm expansion IR:
   - root algorithm から、initialize/config edge、solve/step/update edge、
     nested solver edge、certificate / diagnostic edge を import / execute せずに
     再帰展開する
   - 既定 route は
     `python3 tools/agent_tools/algorithm_expansion_ir.py --python-symbol <path.py::qualname> --target-theorem <target> --format json|markdown`
     とする
   - IR node には `source_symbol`、runtime object、数学的 role、residual unit、
     dtype / backend assumption、proof relevance を持たせる
   - backend arithmetic、IREE FP32、fast-math、denormal、lowered IR などの
     実行基盤前提は IR の `backend_assumptions` に置く。証明のためだけに
     production `InitializeConfig` や algorithm state を増やしてはいけない
   - IR edge には `calls`、`initializes`、`updates_state`、`requests_certificate`、
     `projects_status`、`performance_only` などの関係を持たせる
   - final target theorem から backward slice し、必要な局所 proof obligation と
     不要な implementation detail を分ける。Pyright や型構造でわかる事実は、
     最終命題の数学的依存でない限り証明対象にしない
1. Lemma dependency graph:
   - Algorithm Expansion IR JSON を
     `python3 tools/agent_tools/algorithm_lemma_graph.py --target-profile <profile> --format json|markdown`
     へ渡し、補助命題 graph を生成する
   - lemma node は auxiliary lemma、assumption、target theorem/profile を表す
   - lemma edge は「source lemma が target lemma を消費する」依存を表す
   - lemma id は implementation symbol ではなく IR `node_id` から作る。
     PDIPM、KKT、MINRES、LOBPCG などが同じ `_solve` 名を持つため、
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
   - proof note は探索 log 全体ではなく、現在採用する certified subgraph と
     missing frontier を示す。`verified` と言えるのは checker 済み theorem /
     lemma と、それらだけで接続された target chain に限る
1. Scaffold:
   - `formal_proof.py` で plan、stub、existing proof queries、literature queries を生成する
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
   - Lean/mathlib tactic search、Isabelle Sledgehammer、CoqHammer、SMT solver などを bounded subgoal に使う
   - automation result は再構成・最小化・checker log まで確認する
1. Verification:
   - generated command か project-specific command を実行する
   - log が pass した file / theorem だけを verified にする
   - placeholder、axiom、admit、sorry、unchecked assumption は gap として残す
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
1. Handoff:
   - 学術文章へ戻す場合は `$academic-writing` / `$paper-writing`
   - proof note や長い証明整理文書へ戻す場合は `$academic-writing` または
     `$long-form-writing`
   - 文献・既存 proof の source trail は `$literature-survey`
   - reader-facing report は `$report-writing`

## Required Outputs

```text
proof_claim=<path-or-inline-summary>
proof_plan_json=<path>
proof_plan_md=<path>
proof_existing_queries=<path>
proof_literature_queries=<path>
proof_stub=<path>
proof_library_trace_module=<path>
proof_checker_command=<command>
proof_checker_log=<path|not_run>
proof_status=<verified|refuted|unprovable_under_assumptions|unverified|not_run|blocked>
proof_terminal_outcome=<verified|refuted|unprovable_under_assumptions|open>
proof_impossibility_certificate=<path-or-section-anchor|none>
proof_source_packet=<path>
proof_source_kind=<natural_language|python_ast>
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
proof_initialize_root=<module.initialize|none>
proof_initialize_expansion_graph=<path-or-section-anchor|none>
proof_trace_alignment_check=<command-and-log|not_run>
```

## Proof Status Table

Reader-facing proof notes must include a table shaped like this:

| Claim | Formal theorem / lemma | Implementation surface | Status | Evidence | Remaining obligation |
| --- | --- | --- | --- | --- | --- |
| `<claim>` | `<theorem>` | `<path::symbol>` | `verified` / `refuted` / `unprovable_under_assumptions` / `unverified` / `not_run` / `blocked` | `<checker command/log/counterexample>` | `<gap or none>` |

Use `verified` only for checker-passing artifacts without proof escape hatches.
Use `refuted` only when a counterexample, formal model, or implementation trace
falsifies the target conclusion. Use `unprovable_under_assumptions` only when
there is a checked independence result or a model / witness showing that the
current assumptions do not entail the target claim.
Use `unverified` for prose claims, conditional sketches, assumptions, or
implementation-instantiation obligations that have not been discharged. Use
`not_run` when the checker was unavailable, and `blocked` when a missing
definition, library, or implementation fact prevents progress.
Only `verified`, `refuted`, and `unprovable_under_assumptions` are terminal
outcomes for this skill; all other statuses require more proof work or a
changed claim / assumption ledger.

## Algorithm Expansion IR

実装由来のアルゴリズム証明では、証明本文を書く前にアルゴリズムを
機械的に再帰展開し、中間表現として保持します。これは最終命題から見た
必要十分な局所証明を選ぶための構造であり、IR 自体を `verified` claim には
しません。

1. root は `initialize`、`solve`、`step`、または対象 theorem が消費する
   public algorithm entrypoint から選びます。
1. AST source、`InitializeConfig` ownership、nested solver selection、
   state update、certificate projection、diagnostic construction を node / edge として
   展開します。対象 module を import / execute してはいけません。
   import 先を展開するときも runtime import は使わず、`--root`、慣用的な
   `python/` / `src/`、または明示 `--import-root` にある source file を AST parse
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
   `self.update(...)` のような function-pointer variant は、同一 AST module に
   見える variant function 群へ保守的に展開し、variant selection は static
   dispatch check、各 variant の数学的内容は個別 node として扱います。
1. slice 後に残った各 obligation を、formal theorem、existing proof search、
   literature evidence、または problem-class / backend assumption のいずれかへ
   割り当てます。

Algorithm IR record は次の形を基本にします。

| Field | Meaning |
| --- | --- |
| `ir_node_id` | stable node identifier |
| `source_symbol` | `path.py::qualname` or theorem/source anchor |
| `runtime_object` | `Problem`, `State`, `SolveConfig`, `Info`, residual block, direction, etc. |
| `math_role` | state transition, residual map, direction solve, certificate, or bookkeeping |
| `edge_kind` | call, initialize, state update, certificate request, status projection, or performance-only edge |
| `residual_unit` | residual or norm unit if the node exports numeric evidence |
| `precision_model` | dtype/backend floor or `none` |
| `backend_assumptions` | proof-only backend profile variables and witness obligations |
| `proof_relevance` | required, assumption, helper, performance-only, or excluded |
| `selected_obligation` | local theorem / lemma required by the final target, or `none` |

Static check record は、証明前に機械的に片付く構造制約を表します。

| Field | Meaning |
| --- | --- |
| `check_kind` | constructor resolution or instance method resolution |
| `edge_id` | expansion edge discharged before proof selection |
| `status` | `statically_checked`, `static_checker_required`, or `static_resolution_gap` |
| `proof_effect` | why this edge is removed from proof obligations |

## Lemma Dependency Graph

Algorithm Expansion IR から補助命題を作る段階では、命題を graph として
保持します。一つの algorithm は複数の theorem target を持てるため、補助命題を
一つの線形 list や単一 heading のみで管理してはいけません。

1. `algorithm_lemma_graph.py` で IR JSON から lemma graph を生成します。
   graph node は auxiliary lemma、assumption、target theorem/profile を表し、
   graph edge は「source lemma が target lemma を消費する」依存を表します。
   生成物は初期 graph であり、証明探索では agent / human が overlay として
   補助命題、bridge lemma、dependency edge、proof attempt を追加します。
1. lemma id は IR `node_id` 由来にします。PDIPM、KKT、MINRES、LOBPCG が
   同じ `_solve` などの symbol を持つため、symbol 名だけで lemma を
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

Proof path attempt record は次の形を基本にします。

| Field | Meaning |
| --- | --- |
| `attempt_id` | stable attempt identifier |
| `target_lemma` | lemma or theorem node the attempt tries to discharge |
| `method` | proof assistant, existing-proof search, hand proof, SMT, numeric bound, or literature route |
| `input_evidence` | source theorem, paper, code anchor, checker file, or calculation used |
| `checker_status` | `pass`, `fail`, `not_run`, or `not_applicable` |
| `result_status` | `verified`, `failed`, `blocked`, `assumed`, or `candidate` |
| `adoption_decision` | `adopted`, `rejected`, `superseded`, or `deferred` |
| `next_frontier` | lemma nodes or assumptions still needed after this attempt |

## Initialize-Rooted Proof Expansion

アルゴリズム module が `initialize(config: InitializeConfig)` で下位 solver、
stopping predicate、preconditioner などを再帰的に初期化する場合は、
Algorithm Expansion IR の一部として `InitializeConfig` ownership edge を
展開します。ただし `initialize` 自体を数学的証明の前提にしません。
証明本体は solver / optimizer / stopping / preconditioner ごとの独立 theorem として
保持し、`initialize` はどの独立 proof scope が必要かを列挙する dispatch surface に
限定します。

1. `root_initialize` と `root_config_type` を明記します。
   例: `pdipm.initialize` + `pdipm.InitializeConfig`、
   standalone MINRES なら `minres.initialize` + `minres.InitializeConfig`。
1. `InitializeConfig` の子 field ごとに expansion edge を書きます。
   edge は少なくとも `child_config_field`、`child_initialize`、
   `proof_scope`、`selection_rule`、`role` を持たせます。
   例: `pdipm.InitializeConfig.kkt_initialize -> kkt.initialize`、
   `kkt.InitializeConfig.solver_initialize -> minres.initialize`。
1. method や algorithm family が変わる surface では、caller theorem を
   書き換えず、method registry / variant registry で別 proof scope を選びます。
   下位証明は method ごとに独立させ、caller は選択された scope の certificate を
   top-level substitution lemma に渡します。
1. standalone 利用では、その module の `initialize` を root にします。
   たとえば MINRES 単体の証明展開は `minres.initialize` から始め、
   PDIPM や KKT の proof scope を含めません。
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

| Field | Meaning |
| --- | --- |
| `root_initialize` | root module initialize function |
| `root_config_type` | root `InitializeConfig` type |
| `proof_scope` | independent theorem family required at that root |
| `child_config_field` | field that owns a nested `InitializeConfig` |
| `child_initialize` | nested initialize function selected by that field |
| `selection_rule` | static field, variant tag, or method registry rule selecting the child |
| `role` | correctness certificate, reachability certificate, stopping predicate, or performance-only helper |
| `status` | `verified`, `unverified`, `not_run`, or `blocked` for the proof scope, not for initialization itself |

## Nested Iterative Solver Proofs

外側アルゴリズムが内側の反復法に依存する場合は、反復の証明を
外側 claim へ直結させず、要求精度を上から下へ渡す形にします。

1. 外側 iteration の添字をすべての量に付けます。条件数、スケーリング、
   必要精度、前処理誤差を固定定数に潰してはいけません。固定定数を使う場合は、
   local tube 全体で一様 bound が成り立つことを別 theorem として証明します。
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
