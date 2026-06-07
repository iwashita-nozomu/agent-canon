# agent-orchestration
<!--
@dependency-start
responsibility Documents agent-orchestration for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../workflows/hypothesis-validation-workflow.md analysis-first overlay routing
@dependency-end
-->


## Purpose

task 開始時の mandatory routing skill です。
task を workflow family に分類し、skill set、handoff、review、runtime entrypoint を一貫した形にそろえます。

## Use When

- repository task を開始する
- どの workflow family を使うか決めたい
- skill、subagent、review、model / team policy、run bundle、runtime entrypoint を選ぶ
- prompt、routing、subagent-config の refactor task で、まずどの policy surface を直すか決めたい
- run bundle や review artifact の要否を決めたい
- Codex 内で共通ルールを保ちたい
- user が coding / implementation / patch work の subagent 委譲を明示した

## Core References

- `agents/TASK_WORKFLOWS.md`
- `documents/runtime-profiles-and-check-matrix.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`

## Decision Order

1. 他の task-shape skill を選ぶ前に、この skill で request が `repo-changing execution` か `routing-only/advisory` かを先に分ける
1. `agents/TASK_WORKFLOWS.md` から primary workflow family を 1 つ選ぶ
1. subagent concurrency を次の階層で解決する。`.codex/config.toml` の `[agents].max_threads` は runtime hard ceiling、`agents/task_catalog.yaml` の `workflow_families[].spawn_budget.active_subagents` は workflow active budget、stage wave は parent が active budget 内で切る bounded wave、`workflow_families[].spawn_budget.max_write_subagents` は disjoint write scope を持つ write-capable subagent だけの上限です。Initial Three-Agent Intake は初期責務 wave であり、総同時起動数の cap ではありません
1. repo-changing execution では `team_manifest.yaml` に `run.spawn_budget.active_subagents`、`run.spawn_budget.max_write_subagents`、`run.spawn_budget.runtime_max_threads`、`run.write_scope_policy.max_write_subagents` が分離して出ることを starter / closeout evidence に含める
1. `agents/skills/README.md` から必要最小限の public skill を足す
1. prompt / routing / subagent-config drift が task の中心なら、親が policy prose を直接広く直す前に `prompt_config_reviewer` で prompt/config audit を切る
1. starter command と review / specialist stack を family と mode に合わせて決める
1. repo-changing execution では `python3 tools/agent_tools/check_convention_compliance.py` を closeout gate に入れ、機械化済み規約を prompt 内で再実装しない
1. implementation が scope に入るときだけ Codex routing を出す

mode の意味:

- `repo-changing execution`
  - repo を今から触る
  - run bundle や kickoff command が必要
  - `$codex-task-workflow` を足す
  - `$subagent-bootstrap` は Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の時だけ足す
  - task-shape skill は `$agent-orchestration` の後に足す
- `routing-only/advisory`
  - workflow family、skill、review、starter guidance だけを先に決める
  - full kickoff や repo-changing-only skill を勝手に足さない
  - 普通の相談、壁打ち、説明だけの turn を含む
  - repo state 確認、MCP inventory、repo MCP tool、shell / GitHub check を走らせず、会話だけで応答する
  - user が repo inspection、file edit、validation、PR / issue 処理、CI 確認、または実装作業を求めた時点で `repo-changing execution` へ切り替え、切り替えを user-facing update で明示してから preflight へ進む

## Outputs

- chosen workflow family
- request mode (`repo-changing execution` or `routing-only/advisory`)
- 必要な role / specialist
- review と handoff の最小構成
- repo-editing task なら、workflow family ごとの順序。`Scoped Change Lite` は cheap-first local route、full staged route は requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation
- 最初の作業 update 用の `workflow=<family>`, `skills=<...>`, `review=<...>` 宣言。`skills=<...>` では `$agent-orchestration` を先頭に置く
- PR を作る task では、同じ routing 宣言と `route.py --prompt "<user request>" --format json` の確認結果を PR body、run bundle、または linked comment に残す
- 必要な run bundle command と specialist activation
- `IMPLEMENTATION_CODEX_AGENTS` による `spark_worker` / `worker` routing
- `team_manifest.yaml` の `run.spawn_budget` による active/write/runtime/depth budget の階層
- nested subagent が必要な場合は、`run.delegated_spawn_policy` に owner、child role、入力 packet、expected output、write scope、validation route、review gate を固定します
- parallel write が要るなら file 単位の write-scope 方針

## Workflow Family Mapping

| Task Shape | Primary Family | Notes |
| ---------- | -------------- | ----- |
| one-file / single-abstraction local bug fix or CI/flaky-test fix | `Scoped Change Lite` | `T1`, `T2` |
| local change that needs design, public behavior, workflow, or cross-module validation | `Scoped Change` | `T3` |
| research-backed implementation, benchmark/experiment optimization, academic paper/thesis/scholarly note | `Research-Driven Change` | `T4`, `T5`, `T9`, `T10` |
| large refactor or large multi-surface delivery | `Large Delivery` | `T6`, `T7` |
| environment, CI, Docker, dependency rollout | `Platform And Environment` | `T8` |
| repo-wide workflow/tooling/canon rearchitecture | `Comprehensive Development` | `T11`, `T12` |
| backlog-driven tuning and empirical improvement loop | `Adaptive Improvement Loop` | `T13` |

task id が分かる場合は、task catalog 側の family を正本にします。

## Public Skill Selection

- user が明示した `$skill-name` は preserve します
- `$agent-orchestration` は routing skill として常に先頭に置きます
- `repo-changing execution` では `$codex-task-workflow` を足します
- `$subagent-bootstrap` は Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の時だけ足します
- 非自明な文書作成・改稿で paragraph flow、claim support、または document responsibility が問題になる場合は、共通の構造先行 gate として `prose-reasoning-graph` を足します
- file / document responsibility の判定結果から DSL->文章 adapter を選びます。README、workflow、guide、migration、specification などの一般説明 prose では `long-form-writing` を足します。これは長さではなく責務による選択です
- 投稿論文や thesis chapter の draft では `paper-writing` を優先します
- paper draft ではない scholarly note や broader academic text では `academic-writing` を使います
- scope が paper draft と broader academic prose をまたぐなら、`paper-writing` を優先し、必要なときだけ `academic-writing` を追加します
- PR body、PR evidence comment、status update、decision brief、presentation narrative、PPT storyboard、または tool、JSON / JSONL、hook、eval、checker、experiment、review、audit の結果から reader-facing report を作る場合は `report-writing` を使います。report output は user が HTML、browser view、dashboard、web page、external browser publication を明示しない限り Markdown を既定にします。PPT / deck が scope に入る場合は visual asset plan と slide-production workflow も明示します。raw machine result を保存、コピー、蓄積する場合は `result-artifact-writeout` も併用します
- HTML output、HTML report、browser-readable page、dashboard、local preview server、external browser publication が明示された場合は `html-output` を使います
- HTML の experiment / Eval report が明示された場合は `html-experiment-report` と `html-output` を併用します
- report、experiment plan / report、Eval output、decision brief、presentation / PPT deck、HTML view、document、paper、refactor の構造が非自明な場合、または first figure / table / ponchi-e / slide / section / slice、source map、source-to-slide map、invalid interpretation boundary を先に決める必要がある場合は `structure-planning` を足します
- tool、checker、hook、static analysis を走らせて問題を探す、full finding packet と mechanical priority order を作る、implementation / refactor planning に渡す場合は `tool-finding-report` を使います。before / after impact 比較は明示された場合だけ追加します。raw result を保存する場合は `result-artifact-writeout`、reader-facing narrative を作る場合は `report-writing` も併用します。reader-facing narrative が非自明な finding packet、priority policy、metric / count contract、source map を持つ場合は `structure-planning` も併用します
- README、workflow、guide、migration、specification docs は一般説明 prose adapter を正にしつつ、evidence-backed status、evaluation、audit、review、decision、recommendation section を含む場合は `report-writing` を overlay として足します
- research-backed implementation や比較改善では `research-workflow` を使います
- large refactor では `refactor-loop`、environment task では `environment-maintenance`、repo-wide rearchitecture では `comprehensive-development`、outer loop tuning では `adaptive-improvement-loop` を使います
- アルゴリズムの収束性、停止性、certificate soundness、finite-precision floor、
  solver-chain reachability、または証明可能性のための algorithm change が scope にある場合は
  `algorithm-proof-exploration` と `formal-proof-workflow` を併用します
- directory layout、directory README responsibility、root view、path mapping、responsibility-scope map、source-tree ownership の refactor では `structure-refactor` と `refactor-loop` を併用します
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark、数値 test 診断が scope にある場合は `computational-optimization` を使います
- 原因考察、仮説、修正箇所選定、複数候補比較、change-impact packet 作成、repair-planning / subagent handoff context が task の中心にある場合は `dependency-analysis` を足します。原因仮説を扱う場合は `agents/workflows/hypothesis-validation-workflow.md` を overlay として明示します
- Markdown file edit、docs lint / link / heading repair、docs-check failure、Markdown style drift が scope にある場合は `md-style-check` を足します
- skill / tool / workflow / hook / eval の蓄積ログ分析、routing miss、selection gap、弱い skill の調査が scope にある場合は `agent-log-analysis` を足します
- AgentCanon source update、`vendor/agent-canon` submodule latest / pin update、root runtime view repair、parent AgentCanon update TODO、または `make agent-canon-ensure-latest` / `tools/update_agent_canon.sh` routing が scope にある場合は `agent-canon-update` を足します。parent repo の `canon-pin` branch lane が必要な場合だけ `agent-update-branch` も併用します
- user / reviewer feedback が agent 行動、routing miss、再発防止、task retrospective、agent-side memory update を要求する場合は `agent-learning` を足します
- 関係のない family skill は足しません
- tool 化済みの規約検証は task-shape skill として増やさず、`check_convention_compliance.py` の gate に委譲します

## Entrypoint Precedence

- repo-editing task や kickoff command が必要な task では `bootstrap_agent_run.py` を優先します
- `task_start.py` は routing-only starter guidance に向きます
- `task id がある` ことだけでは `task_start.py` を優先する理由にはなりません。repo-changing execution なら task id 付きでも bootstrap を使います

## Review And Specialist Expectations

- family に応じた reviewer / specialist stack まで出します
- `Research-Driven Change` では research / report / reproducibility / benchmark / artifact 系 reviewer を落としません
- 一般説明 prose adapter を使う docs では、docs-impact がある場合に `document_flow_reviewer` と docs completeness review を使います
- academic/paper work では notation / logic review を落とさず、paper draft では `citation_evidence_reviewer` も追加します

## Codex Implementation Routing

- implementation が scope に入るときだけ routing を出します
- `bootstrap_agent_run.py` か `task_start.py` の output で `IMPLEMENTATION_CODEX_AGENTS` を確認してから route します
- prompt/config drift を含む task では、routing 決定後の詳細 diff を `prompt_config_reviewer` に監査させ、親が chat 文脈だけで共有 policy surface を広く書き換えません
- user が coding / implementation / patch work の subagent 委譲を明示した task は、read-only survey / review role だけで完了扱いにしません。requirements、bounded `allowed_paths`、write scope、validation plan、tool-rejection preflight が固定できたら、追加の read-only wave より先に `spark_worker` / `worker` を起動または schedule します。
- Runtime authorization や tool gate で write-capable subagent を起動できない場合は、`WRITE_SUBAGENT_AUTHORIZATION=required` または gate-specific blocker を run bundle に残します。parent-direct 実装は、その blocker を記録した後の fallback として扱います。
- Routine docs / Focused code では parent-direct を許可します。subagent 実装では、design trace、identifier naming、test plan、write scope が固定済みで、1 file または単一抽象ユニット、public interface 変更なし、依存追加なし、仕様解釈なし、局所 validation で閉じる低リスク slice は `spark_worker` を先に使います。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。
