# agent-orchestration
<!--
@dependency-start
contract skill
responsibility Documents agent-orchestration for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../workflows/hypothesis-validation-workflow.md analysis-prioritized overlay routing
upstream design ../COMMUNICATION_PROTOCOL.md pre-edit investigation and fresh subagent context packets
@dependency-end
-->


## Reader Map

- Purpose: mandatory repository-task routing that selects workflow family,
  active skills, roles, reviews, run bundle, and implementation route.
- Section path: Purpose, Use When, and Core References orient the reader;
  Decision Order contains the operational rules; Outputs, Workflow Family
  Mapping, Public Skill Selection, Entrypoint Precedence, Review And Specialist
  Expectations, and Codex Implementation Routing define the routing result.
- Use when: starting any repository task or choosing workflow, skill, subagent,
  review, runtime entrypoint, or run-bundle policy.
- Boundary: this skill routes and records the packet; task-specific execution
  stays with the selected workflow and task-shape skills.

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
- repo-wide / multi-surface の repo-changing task で、独立して差し替え可能な作業単位だけを multi-agent wave に切りたい
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
1. repo-changing execution で実装 owner が明示 path と source packet でまだ固定されていない場合は、編集 path を選ぶ前に `agent-canon local-llm route-implementation-surface --request-file <request.txt> --format text` を走らせる。`PRIMARY_SURFACE`、`PRIMARY_PATHS`、`FORBIDDEN_PATHS`、`REQUIRED_PRE_EDIT_CHECKS` を source packet seed にし、write-capable handoff では `PRIMARY_PATHS` を `allowed_paths`、`FORBIDDEN_PATHS` を `do_not_read` に流す。LocalLLM が無い場合は deterministic fallback output を provisional source-packet seed として使うか、`router_unavailable_blocker` として記録し、responsibility search と dependency scope で edit path を確定する。fallback routing は `fallback_exit_status` として `canonical_rerun_pass`、`durable_blocker_or_issue`、`explicit_approval_evidence` のいずれかに接続する
1. 広い prose 読み込み、raw log 探索、subagent 起動の前に、その判定を正本として持つ canonical tool があるか確認する。tool-covered surface では tool を先に呼び、pass / finding の compact output を信頼し、修正に必要な path / line / bounded slice だけを読む
1. 調査、レビュー、追加確認は、継続前に次に進む作業を記録します。次の作業は、経路決定、編集場所の決定、検証、Issue 記録、担当者付きの保留、対象外記録のいずれかです。次の作業が同じ場合は、現在の記録の補助根拠に圧縮して、実装、検証、Issue 処理へ戻ります。
1. 重い計算系コマンドを予定する前に、タスクに結び付いた実行前の確認記録を作るか引用します。確認記録には、依頼の対応箇所、コマンドの種類、先に使った軽量な根拠、見込み時間、使う資源、停止条件、成果物の場所、担当者を入れます。重い計算系コマンドには、CI 全体、長いテスト一式、ベンチマーク、実験、GPU / CPU 数値実行、ソルバーの一括確認、大きな乱択ケースが含まれます。
1. 編集 path、parent-direct 実装、または write-capable subagent handoff の前に、調査量を task risk に合わせる。広い surface、未確定 path、multi-agent handoff では `agents/COMMUNICATION_PROTOCOL.md` の `Pre-Edit Repository Investigation Packet` を作るか引用する。明示 path、1 file / single abstraction、Routine docs、Focused code、typo / link / format-only では、owner、対象 path、reuse 根拠、validation route だけを短く記録して進める。raw search hits、nearest editable file、または chat context だけで調査完了扱いにしない
1. `agents/TASK_WORKFLOWS.md` から primary workflow family を 1 つ選ぶ
1. repo-changing task では parent-direct を既定経路にし、multi-agent write-capable wave は user が求めた場合、または独立して差し替え可能な target 群があり並列化で実作業が減る場合だけ使う。repo-wide、multi-surface、長文文書群、shared runtime surface というだけでは multi-agent を起動しない。write-capable handoff が runtime authorization や tool gate で詰まる場合は、parent-direct に黙って縮退せず、run bundle に blocker と fallback_exit_status を記録する
1. multi-agent にする場合でも、分割境界は `差し替え可能な単位` に限る。別実装、別証明、別文書責務、別 validation oracle、別 review decision に置き換え得る境界だけを slice / wave / worker scope にする。数理的に差し替えが発生しない境界、単なる記法・読解補助・固定 context・同じ oracle を共有する連続導出は分割せず、同じ packet と同じ owner scope に残す
1. subagent concurrency を次の階層で解決する。`.codex/config.toml` の `[agents].max_threads` は runtime hard ceiling、`agents/task_catalog.yaml` の `workflow_families[].spawn_budget.active_subagents` は workflow active budget ceiling、stage wave は parent が current stage の evidence と dependency order から切る bounded wave、`workflow_families[].spawn_budget.max_write_subagents` は disjoint write scope を持つ write-capable subagent だけの上限です。Intake Responsibility Wave は責務 intake wave であり、family budget を埋める target ではありません。後続 role / skill は dynamic expansion wave として evidence gate で追加します。独立 workstream は同一階層の flat wave ではなく、stage owner ごとの vertical dynamic wave chain として扱います
1. repo-changing execution では `team_manifest.yaml` に `run.spawn_budget.active_subagents`、`run.spawn_budget.max_write_subagents`、`run.spawn_budget.runtime_max_threads`、`run.write_scope_policy.max_write_subagents` が分離して出ることを starter / closeout evidence に含める
1. prompt-derived skill routing が必要なら `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` を使い、`ACTIVE_SKILLS` を current stage の宣言、`DEFERRED_SKILLS` を後続 wave trigger として扱う。`task_start.py` / `bootstrap_agent_run.py` を使う場合は、`SUGGESTED_SKILLS`、`ACTIVE_SKILLS`、`DEFERRED_SKILLS` と `run.repo_tool_routing_policy` を同じ source packet として保持し、`REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` から later wave の skill を追加したらその skill の command packet を再生成する
1. `agents/skills/README.md` から current stage に必要な public skill だけを足す。routing update に全 skill family を列挙せず、後続 stage で必要になった skill を wave ごとに追加する
1. repo-changing execution の編集では、選択済み runtime `SKILL.md` の本文を読む。これは `Scoped Change Lite`、Routine docs、Focused code、typo / link / format-only、parent-direct route を含む selected_runtime_skill_read 契約です。patch 前の作業 evidence に small_change_skill_read、skill 名、path を残す
1. 1 file / single abstraction、Routine docs、Focused code、typo / link / format-only、明示的な小規模修正では `$small-change-routing` を追加し、selected_runtime_skill_read、small_change_skill_read、targeted validation をそこで固定する。小規模修正は routing と validation profile の signal であり、実装 behavior は契約完全実装ポリシーから導く
1. prompt / routing / subagent-config drift が task の中心なら、親が policy prose を直接広く直す前に `prompt_config_reviewer` で prompt/config audit を切る
1. starter command と review / specialist stack を family と mode に合わせて決める
1. repo-changing execution では `python3 tools/agent_tools/check_convention_compliance.py` を closeout gate に入れ、機械化済み規約を prompt 内で再実装しない
1. implementation が scope に入るときだけ Codex routing を出す
1. tool が既に check した property を `explorer` や read-only reviewer に再読解させない。subagent へ渡すのは compact tool artifact と bounded finding scope で、tool output が必要な抽象を欠く場合は tool contract の不足として扱う

mode の意味:

- `repo-changing execution`
  - repo を今から触る
  - run bundle や kickoff command が必要
  - `$codex-task-workflow` は execution stage で足す
  - `$subagent-bootstrap` は Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の handoff / wave が ready になった stage で足す
  - task-shape skill は `$agent-orchestration` の後に足す
- `routing-only/advisory`
  - workflow family、skill、review、starter guidance だけを先に決める
  - full kickoff や repo-changing-only skill を勝手に足さない
  - 普通の相談、壁打ち、説明だけの turn を含む
  - repo state 確認、shell / GitHub check を走らせず、会話だけで応答する
  - user が repo inspection、file edit、validation、PR / issue 処理、CI 確認、または実装作業を求めた時点で `repo-changing execution` へ切り替え、切り替えをユーザー向け update で明示してから preflight へ進む

## Outputs

- chosen workflow family
- request mode (`repo-changing execution` or `routing-only/advisory`)
- 必要な role / specialist
- 契約に必要な review と handoff 構成
- `Pre-Edit Repository Investigation Packet` の path または parent-direct rationale
- repo-editing task なら、workflow family ごとの順序。`Scoped Change Lite` は cheap local route、full staged route は requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation
- 着手時の作業 update 用の `workflow=<family>`, `skills=<active-now>`, `review=<...>` 宣言。`skills=<...>` では `$agent-orchestration` を先頭に置き、後続 skill は dynamic wave trigger として run bundle 側へ残す
- PR を作る task では、同じ routing 宣言と `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を PR body、run bundle、または linked comment に残す
- 必要な run bundle command と specialist activation
- `IMPLEMENTATION_CODEX_AGENTS` による `spark_worker` / `worker` routing
- `team_manifest.yaml` の `run.spawn_budget` による active/write/runtime/depth budget の階層
- nested subagent が必要な場合は、`run.delegated_spawn_policy` に owner、child role、入力 packet、expected output、dependency-expanded handoff scope、validation route、review gate を載せます
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
- `repo-changing execution` が始まる stage では `$codex-task-workflow` を足します
- `$subagent-bootstrap` は explicit handoff / wave が ready になった stage、または Shared canon / Large delivery / high-risk / multi-step / explicit subagent work で bootstrap evidence が必要な stage だけ足します
- 非自明または substantive な文書作成・追記・改稿で section order、reader path、claim support、source map、canonical route、または document responsibility が変わる場合は、共通の構造先行 gate として `prose-reasoning-graph` と `structure-planning` を足します。typo / link / format-only では `md-style-check` を使い、`structure_contract=skipped` と理由を残します
- file / document responsibility の判定結果から DSL->文章 adapter を選びます。README、workflow、guide、migration、specification などの一般説明 prose では `long-form-writing` を足します。これは長さではなく責務による選択です
- 投稿論文や thesis chapter の draft では `paper-writing` を優先します
- paper draft ではない scholarly note や broader academic text では `academic-writing` を使います
- scope が paper draft と broader academic prose をまたぐなら、`paper-writing` を優先し、必要なときだけ `academic-writing` を追加します
- PR body、PR evidence comment、status update、decision brief、presentation narrative、PPT storyboard、または tool、JSON / JSONL、hook、eval、checker、experiment、review、audit の結果から reader-facing report を作る場合は `report-writing` を使います。report output は user が HTML、browser view、dashboard、web page、external browser publication を明示しない限り Markdown を既定にします。PPT / deck が scope に入る場合は visual asset plan と slide-production workflow も明示します。raw machine result を保存、コピー、蓄積する場合は `result-artifact-writeout` も併用します
- HTML output、HTML report、browser-readable page、dashboard、local preview server、external browser publication が明示された場合は `html-output` を使います
- HTML の experiment / Eval report が明示された場合は `html-experiment-report` と `html-output` を併用します
- report、experiment plan / report、Eval output、decision brief、presentation / PPT deck、HTML view、document、paper、refactor の構造が非自明な場合、または primary figure / table / ponchi-e / slide / section / slice、source map、source-to-slide map、invalid interpretation boundary を先に決める必要がある場合は `structure-planning` を足します
- tool、checker、hook、static analysis を走らせて問題を探す、full finding packet と mechanical priority order を作る、implementation / refactor planning に渡す場合は `tool-finding-report` を使います。before / after impact 比較は明示された場合だけ追加します。raw result を保存する場合は `result-artifact-writeout`、reader-facing narrative を作る場合は `report-writing` も併用します。reader-facing narrative が非自明な finding packet、priority policy、metric / count contract、source map を持つ場合は `structure-planning` も併用します
- README、workflow、guide、migration、specification docs は一般説明 prose adapter を正にしつつ、evidence-backed status、evaluation、audit、review、decision、recommendation section を含む場合は `report-writing` を overlay として足します
- research-backed implementation や比較改善では `research-workflow` を使います
- large refactor では `refactor-loop`、environment task では `environment-maintenance`、repo-wide rearchitecture では `comprehensive-development`、outer loop tuning では `adaptive-improvement-loop` を使います
- directory layout、directory README responsibility、root view、path mapping、responsibility-scope map、source-tree ownership の refactor では `structure-refactor` と `refactor-loop` を併用します
- task 開始前に expected AgentCanon repo structure、root view、`vendor/agent-canon/`、`.gitmodules`、または canonical path の欠落 / 移動 / stale state が疑われる場合は、通常 task の前に `structure-refactor` の pre-task structure repair route を使います。AgentCanon-owned root view / submodule drift なら `agent-canon-update` も併用します
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark、数値 test 診断が scope にある場合は `computational-optimization` を使います
- 原因考察、仮説、修正箇所選定、複数候補比較、change-impact packet 作成、repair-planning / subagent handoff context が task の中心にある場合は `dependency-analysis` を足します。原因仮説を扱う場合は `agents/workflows/hypothesis-validation-workflow.md` を overlay として明示します
- Markdown file edit、docs lint / link / heading repair、Mermaid / math drift、formatter adjacent check、`agent-canon docs`、docs-check failure、Markdown style drift が scope にある場合は `md-style-check` を足します。substantive な文書変更は `prose-reasoning-graph` と `structure-planning` も併用します
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
- user が coding / implementation / patch work の subagent 委譲を明示した task は、read-only survey / review role だけで完了扱いにしません。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、追加の read-only wave より先に `spark_worker` / `worker` を起動または schedule します。
- Runtime authorization や tool gate で write-capable subagent を起動できない場合は、`WRITE_SUBAGENT_AUTHORIZATION=required` または gate-specific blocker を run bundle に残し、`fallback_exit_status` を `canonical_rerun_pass`、`durable_blocker_or_issue`、`explicit_approval_evidence` のいずれかへ接続します。parent-direct 実装へ進める route は、実装前に選ばれた Routine docs / Focused code か、明示承認 evidence 付きの revised workflow route です。
- Routine docs / Focused code では、risk class と check matrix が実装前に選択された場合に parent-direct を使います。subagent 実装では、Abstract Design Frame から導かれ、design trace、identifier naming、test plan、dependency-expanded handoff scope が揃い、1 file または単一抽象ユニット、public interface 変更なし、依存追加なし、仕様解釈なし、局所 validation で閉じる低リスク slice は `spark_worker` を先に使います。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。
