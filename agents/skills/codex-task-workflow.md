# codex-task-workflow

<!--
@dependency-start
contract skill
responsibility Documents codex-task-workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit investigation and context capsule handoff packets
upstream design ../../documents/design/dependency-manifest-design.md defines dependency manifest requirements
upstream design ../../documents/operations/BRANCH_SCOPE.md defines Git commit correctness and push evidence
upstream design tool-finding-report.md tool-based finding packet and prompt feedback workflow
upstream design ../internal-routines/design-implementation-correspondence.md design read/fingerprint/handoff correspondence route
upstream design ../../documents/design/request-intent-and-update-relation.md compact task-packet request and update projection
downstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

implementation stage に入る前に、
`../internal-routines/design-implementation-correspondence.md` の design read と
clause fingerprint route を task packet に接続します。この skill は task
stage の transport owner であり、対応 policy を複製しません。

### Compact request/update projection

`documents/design/request-intent-and-update-relation.md` の flow を task packet の既存
request clauses、active state、validation route へ投影します。質問は evidence-read と
answer completion で閉じ、explicit write clause は owner handoff に進み、追加入力は
既存 packet の sparse delta として read-back します。
追加・変更 clause は既存 write gate の readback 後に、goal/artifact/order/handoff の
既存 delta fields として task packet へ投影されます。

質問の operation は evidence-read、resulting state は answer-complete、completion evidence
は evidence-backed answer と task-packet readback です。explicit write clause の operation
は owner handoff、resulting state は write-ready、completion evidence は owner/write-set/
acceptance readback です。update の operation は compatible active context への overlay、
resulting state は sparse delta、completion evidence は changed-clause と delta readback
です。worker は selected design と DIC closure packet を implementation 前に読み、review
は changed path から design clause への reverse trace を readback します。

task packet は DIC `DIC-010` の path+section+clause/ref closure packet を保持し、
DIC の closure readback 後に worker handoff を開始します。traversal policy は DIC が所有します。

- Purpose: gives Codex a context-independent repository task execution path
  from intake through validation and closeout.
- Use When: a repo-changing task needs artifact placement, implementation
  routing, validation, reviews, or closeout evidence.
- Section path: Purpose, Use When, and Core Reference orient the route; Stages
  gives the operational flow; Required Output names the completion packet.
- Boundary: task-specific behavior still comes from the user-request clauses,
  source packet, selected skills, and validation route.

## Purpose

Codex が会話コンテキストに依存せず、毎回同じ順序で task を進めるための標準フローです。

## Use When

- Codex で task を最初から最後まで進める
- 手順を固定したい
- task ごとの skill 選択を標準化したい

## Core Reference

- `agents/canonical/CODEX_WORKFLOW.md`

## CompletionCoverage Reader Projection

Closeout reporting consumes the generated `agent-canon.completion-coverage.v1`
projection from the existing run-bundle logical ledger. This skill is a reader
and routing projection; `COMMUNICATION_PROTOCOL` owns the schema,
`CODEX_WORKFLOW` owns applicability/state, and `report_artifact_checks` plus
`task_close` own checking/consumption. Preserve the five mapping error sets,
typed owner/state/API/dependency evidence, W1 certificate references, and both
independent predicates `all_planned_chunks_complete` and
`overall_delivery_complete`. Do not aggregate a second coverage map or turn a
chunk/checkpoint into delivery.

Use `tools/bin/agent-canon docs check <changed-markdown-paths>` as the single
Markdown/math/Mermaid route and consume the single official
`agent-canon.posttooluse-stop.v1` PostToolUse/Stop dispatcher output. The
CompletionCoverage route has no scalar OOP score, line/length, test-count,
coverage, mutation, private-helper, or checker-retest completion gate.

## Stages

1. intake and semantic decision sufficiency
1. owner-critical context and validation route
1. workflow and skill selection
1. optional durable artifact placement when coordination or resumption needs it
1. optional subagent bootstrap for a launchable wave
1. selected implementation
1. selected validation and review
1. closeout

The stages are conditional route points, not a fixed plan-review-edit sequence.
Task-catalog roles, default review packs, and related skills are candidates;
they become work only when an owner-critical operation, unresolved branch, or
selected validation route activates them. A wave is launchable only when its
owner, replaceable responsibility, context, write authority, and validation
route are ready.

## Required Output

- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- `task_start.py` / `bootstrap_agent_run.py` が出す
  `REPO_TOOL_ROUTING_SEQUENCE`、`REPO_TOOL_ROUTING_NEXT_COMMAND`、
  `REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` は、選択された route が必要と
  する場合にだけ handoff または durable packet へ渡す。構造化された
  handoff message/tool result が意味上十分なら、それを packet として扱い、
  file-backed run-local packet は coordination または resumption のために
  必要な場合だけ作る
- Shared canon / Large delivery / high-risk / multi-step task でも、
  `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` は
  coordination、resumption、または選択された launchable wave が必要と
  する場合にだけ実行する。作業が repo を変更することだけでは bundle の
  根拠にならない
- owner-bounded route では boundary-evidenced local route を使い、document-flow / broad design review は escalation 条件がある場合だけ起動する
- repo-changing implementation / patch / doc-edit work では、別の writer
  が必要なときだけ selected write-capable implementer handoff を bootstrap
  または schedule する。owner、責務、context、write authority、validation
  route が互換な active agent は revised scope でも再利用する。独立 review、
  disjoint write authority、互換性のない owner/context、または context
  integrity failure の場合だけ fresh agent を起動する。parent-direct repo
  edit は、別 writer が不要な場合でも明示承認または spawn/tool gate blocker
  の例外証拠を記録する既存ルートに従う
- Routine docs / Focused code でも targeted validation は使うが、
  task-catalog の role や default review pack は候補であり、selected
  owner-critical operation または unresolved branch が有効化した場合だけ
  handoff、review、wave を作る
- repo-changing execution の編集では、既存 tool の実行や owner-bounded patching の前提として runtime `SKILL.md` 読了を要求しません。対象 property を正本として持つ既存 tool または command packet を先に使い、結果の解釈や修正に必要な owner surface だけを開きます。owner boundary、差し替え可能な単位、targeted validation route、public impact boundary が evidence で閉じた修正は `$owner-bounded-routing` に流し、owner boundary、existing-tool route、targeted validation を evidence に残す。外形的な作業量や file 数だけでは route を固定しません。実装 behavior は契約完全実装ポリシーから導く
- research-backed implementation、benchmark、external research、prior art、
  公式 docs、文献由来の design decision によって code、protocol、report claim、
  design を変える場合は、`skills=...` / run bundle の skill call sequence で
  `literature-survey` を `research-workflow`、設計、implementation より先に
  呼びます。durable source packet、source class、
  limitation、contrary / narrowing evidence、adoption/exclusion decision を
  `Implementation Source Packet` に接続し、post-hoc citation cleanup や一時的な
  browser context から実装 claim を閉じません。
- ユーザーが coding / implementation / patch / editing を明示的に依頼した場合は、read-only wave を completion ルートにしない。要件整理、surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation route、`tool_rejection_preflight` evidence から dependency-expanded handoff scope を作り、選択済み write-capable implementer を起動してから実装へ進む
- repo-changing implementation / patch / doc-edit task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` を併用して selected write-capable implementer handoff を既定 route にする。parent-direct は明示承認または subagent spawn / tool gate blocker を記録した例外 route としてだけ使う
- workflow family、public skill set、review stack は `agent-orchestration` の出力を入力として受け取り、この skill で routing matrix を重複定義しない
- ユーザー向けの作業報告、最終報告、レビュー要約、handoff guidance、reader-facing docs は日本語で書きます。内部の項目名、列挙値、役割名、補助関数風の語は、コマンド、パス、表、正確な根拠の引用に閉じます。専門語が必要な場合は、既存のリポジトリ用語または外部標準の用語を使い、自然文で説明します。
- AgentCanon update surface が repairable なら `AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> make agent-canon-ensure-latest` を実行する。submodule repo では親 repo の無関係な dirty state はこの実行を block しない。update surface 自体が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon PR / proposal merge 後に `AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰る
- AgentCanon source、submodule pin、`.gitmodules`、AgentCanon-owned root
  runtime view、root-copy surface、または parent root sync を変更した場合は
  `agentcanon_structure_followup=required` を記録する。template / derived
  parent root で `bash tools/sync_agent_canon.sh link-root` と
  `bash tools/sync_agent_canon.sh check` が pass した後にだけ
  `agentcanon_structure_followup=pass` を記録して closeout evidence に使う。
- commit / push の前に `documents/operations/BRANCH_SCOPE.md` の commit correctness contract と範囲分割契約を満たす。commit は Git 上の実行単位、PR はレビュー単位として扱い、validation が参照した source、config、schema、fixture、文書、tool entrypoint を tracked tree に含める。複数の問題、canonical owner、behavior or contract delta、validation route にまたがる差分は範囲表を作り、merge 前に別 PR または別 commit へ分ける。code 変更では file-level code dependency と関数 / public entrypoint 単位の call-site evidence も残す。evidence には branch、commit SHA、submodule SHA、validation command、対象 path、残った dirty / untracked path の分類を残す
- 普通の相談、壁打ち、routing-only advice、説明だけの turn はこの skill の実行対象ではありません。その場合は shell / GitHub checks を走らせず、会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させない
- request clauses から `requested_scope` を先に固定し、その後に owner boundary、dependency evidence、validation route から `work_scope` を導く。限定された `work_scope` は実装段階の packet としてだけ使えます。broader request を閉じるには `covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` を明示し、要求された surface を勝手に外していないことを示します。
- `documents/`、`notes/`、`references/`、local implementation directories を広く読む前に、`agents/COMMUNICATION_PROTOCOL.md` の `Structure Intake Packet` を作るか引用します。構造読み込み artifact を owner、document、implementation surface 選択の入口にし、exact prose excerpt は次の判断に効くと packet で分かった後に昇格します。
- 編集手段は、手編集で責務を追える差分では patch-based edit、機械生成・一括変換では repo script / formatter の順に選ぶ
- sweep と原因調査は、次の具体的な作業に結び付けます。各結果は、実装経路、再利用判断、古い面の修復、依存範囲、検証経路、Issue、または担当者付きの保留のどれかを更新します。更新先が同じ根拠は記録内の短い引用に圧縮し、現在の作業へ戻ります。
- 検証は静的解析・読み取り evidence を主証跡にします。静的解析、依存確認、
  文書確認、経路確認、source / contract の読み取り、変更ファイル対象の
  test を primary validation evidence として先に使います。動作確認、smoke
  run、CI 全体、長いテスト一式、ベンチマーク、実験、GPU / CPU 数値実行、
  ソルバーの一括確認、大きな乱択ケースは、runtime behavior 変更、
  integration risk、または静的解析・読み取りで残った未解決 finding がある
  場合の supplemental evidence としてだけ使います。広い実行を予定する前に、
  静的解析・読み取りで何が未確認として残ったかを記録します。
- 詳細設計が編集対象 path に絞る前に、責務 model、概念 graph または layer model、非対象、将来拡張 layer、評価軸、canonical surface 関係を含む `Abstract Design Frame` を書くか引用する。実装 scope、file list、validation は nearest editable path や current finding ではなく、この frame から導く
- 実装 path を選ぶ前に、承認済み design packet が owner、canonical paths、forbidden paths、required checks をすでに固定していない限り、`python3 tools/agent_tools/search.py --query-file <request-or-design-question.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json` を走らせるか引用する。bounded candidate path を source packet seed にし、responsibility search と dependency scope で owner、edit scope、forbidden path を確定する。deterministic search が失敗した場合は path selection を `router_unavailable_blocker` へ遷移させ、owner、responsibility、dependency evidence が一つの canonical route を示した時点で継続する
- 編集前の repo 調査は `agents/COMMUNICATION_PROTOCOL.md` が所有する `Pre-Edit Repository Investigation Packet` として固定する。既存 repo 調査が甘いまま実装へ進んだ場合は、差分を広げる前にこの packet を作り直す
- `Pre-Edit Repository Investigation Packet` は、次に進む具体的な作業と担当者を 1 つ書いて閉じます。別の探索へ広げる前に、その作業を実装、検証、Issue 処理のいずれかへ進めます。
- 検証経路は、primary validation evidence として使った静的解析・読み取り、
  広い実行が supplemental かつ承認済みか、担当者の 3 点を書いて閉じます。
  方針、文書、メタデータ、契約だけの薄い包み、既存の確認コマンドが所有する
  性質では、静的確認だけを使います。
- validation の test / check failure を見た場合は、implementation intent の変更、
  behavior / test の削除、revert、oracle weakening、pass 目的の単純化、
  validation downscope へ進む前に、`failing_contract`、`observation_level`、
  `cause_classification`、`intent_preservation`、`evidence` を記録する。
  `intent_preservation` は same-intent repair / escalation route を示す。
  implementation bug は approved intent を保って修正し、test oracle / spec mismatch
  は test / design evidence を修正し、fixture / environment / stale generated
  artifact は owner route を修正し、unrelated failure は residual route に分ける。
  approved-design / user-request conflict は intent を変える前に escalation する。
- 実装前に Design Integrity Gate を閉じます。`Abstract Design Frame` または
  parent-direct の design-boundary note は、責務 model、差し替え可能な単位、
  非対象、validation route を file-level work より先に示します。API shape、
  責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、
  runtime contract、config surface の判断不足は `design_issue_blocker` として
  扱い、implementation shortcut にしません。
- 実装前に承認済み `design_brief.md` の `Abstract Design Frame`、`Implementation Source Packet`、`Design Side-Effect Map`、`Design-To-Implementation Trace` を読み、各 implementation slice と downstream side effect が抽象責務 model から導かれていることを確認してから design artifact path、design section、test-plan item、user-request clause ID を引用する
- 実装中に設計上の問題を見つけたら、勝手に実装で吸収せず `design_issue_blocker` と evidence を記録して詳細設計 / design review へ戻る。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾を、local fallback、wrapper、helper、分岐、互換 route、test 緩和、説明だけの上書きで処理してはいけない
- implementation slice は contract-complete implementation として閉じる。request clause、acceptance contract、`Implementation Source Packet`、validation route を結び、要求を縮める implementation shortcut を見つけたら `design_issue_blocker` と evidence を記録して design review へ戻る
- 見た目の広さ、`Owner-Bounded Change`、MVP、thin slice は暫定的な routing、wave、validation profile の signal に留めます。実装 behavior は request clauses、acceptance contract、implementation source packet、design trace、dependency-expanded scope、validation route、review gate から導き、owner boundary や impact surface が違うと分かった時点で route を更新します。
- 同じ implementation pass で直せるのは、承認済み design、局所 precedent、既存責務境界から一意に導ける typo、format、import、狭い機械的追従だけです。判断が必要なら設計問題として扱う
- class、dataclass、`Protocol`、継承、public API、型境界、依存方向を触る implementation slice は `$oop-readability-check` を validation route に入れ、SOLID principle signal、OOP dimension、finding kind、`tools/oop/shared/readability_core.py` の mapping を design artifact に結びます。
- SOLID-sensitive な Python slice は `python3 tools/agent_tools/check_solid_evidence.py --changed --evidence <oop-readability-report>` で、OOP readability report の `scanned_paths` が changed path を覆うことを確認します。
- 実装前に `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認します。`worker` が既定で、`spark_worker` は Abstract Design Frame と design trace から導かれた bounded slice に対し、parent packet が `--select-agent-type implementer=spark_worker:<evidence>` を明示し、stdout / manifest が選択を記録した場合だけ使います。選択済み candidate が blocked の場合は local/tool context に `selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、`parent_packet_ref`、`status=blocked` を記録し、candidate を変える場合は parent packet と wave の改訂を必須にします
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- parent 直編集でも write-capable subagent でも、実装前に cause investigation artifact を固定し、`Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残してから code edit に入る
- parent 直編集でも write-capable subagent でも、実装前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、予測された cause investigation / OOP / helper / dependency / responsibility_scope / hook runtime / skill mirror / tool catalog / protocol / log-surface gate と repair plan を handoff または work log に残す。実装ディレクトリを選ぶ前に owner scope と protecting tools を記録する
- fresh subagent に渡す prompt は chat history 依存にしない。`agents/COMMUNICATION_PROTOCOL.md` が定義する `Fresh Subagent Context Capsule` を渡し、full transcript、raw logs、full dashboard、repo root 全体を context として渡さない
- runtime/tool gate が write-capable spawn を阻害する場合は `WRITE_SUBAGENT_AUTHORIZATION=required` または該当 gate blocker を local/tool evidence として記録し、`selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、`parent_packet_ref`、`status=blocked` を明示する。継続する際は `canonical_rerun_pass`、`durable_blocker_or_issue`、`router_unavailable_blocker`、`explicit revised route` 付きの approved route に限定する。
- 既存的な `status=blocked` の timeout 回復では、同一内容での再待機は行わず、`new state evidence` または `revised parent packet` がある場合のみ再 wait/再評価し、ユーザー向けの fallback message は出さない
- tool / checker / hook / reviewer / subagent feedback から実装へ入る場合は `tool-finding-report` で finding packet を作り、write-capable subagent handoff に artifact path、structured findings、prompt feedback decision を渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` が出た場合は、次の write-capable subagent を起動する前に handoff prompt、skill、workflow、または task catalog prompt を修正する
- prompt/config drift が shared canon surface をまたぐ場合は、親がその場で prose を増やす前に `prompt_config_reviewer` で audit し、この workflow はその監査結果と契約から導かれる差分を適用する
- nontrivial document creation / revision では `prose-reasoning-graph` と `structure-planning` を構造先行 gate として通し、その後に `long-form-writing` / `paper-writing` / `academic-writing` へ渡す。typo / link / format-only では `md-style-check` と `structure_contract=skipped` の理由を evidence に残す
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
- Shared canon / Large delivery / high-risk / workflow-tooling change では closeout 前に `python3 tools/agent_tools/check_convention_compliance.py` を通し、workflow prohibition、convention tool gate、skill-routing hook の欠落を tool で検出する
- 検証は該当する範囲で静的解析・読み取り route から始めます。広い実行は
  実行前の確認記録を使い、静的解析・読み取りで残った未確認点を記録します。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/canonical/CODEX_WORKFLOW.md`.
1. Route skill selection through `$agent-orchestration` first; this skill executes the selected Codex task flow after routing is selected.
1. Run `make agent-canon-ensure-latest` before planning or implementation when the AgentCanon update surface is repairable. In submodule repos, the blocking scope is the AgentCanon update surface. If the update surface itself is unsafe to refresh, route it through `agents/workflows/agent-canon-pr-workflow.md` or `agents/workflows/derived-agent-canon-diff-workflow.md`, merge the AgentCanon PR or proposal first, then rerun `make agent-canon-ensure-latest` and `bash tools/sync_agent_canon.sh link-root` in the template / derived repo.
1. When AgentCanon source, submodule pin, `.gitmodules`, AgentCanon-owned root runtime view, root-copy surface, or parent root sync changes, record `agentcanon_structure_followup=required`. Use `bash tools/sync_agent_canon.sh link-root` and `bash tools/sync_agent_canon.sh check` in the template / derived parent root, then record `agentcanon_structure_followup=pass` only after both commands pass.
1. Ordinary consultation, brainstorming, routing-only advice, and explanation-only turns are conversational turns. For those, keep MCP config inspection, shell commands, and GitHub checks in hold until the user requests state inspection, file edits, validation, PR/issue processing, CI checks, or implementation work, and continue with conversational responses until then.
1. MCP is a Codex config/runtime surface. Root `mcp/` is a removed legacy path. For repository tasks that change MCP config or MCP-dependent gates, inspect `.codex/config.toml`, the owner docs, and the changed files directly; root `mcp/` remains a removed legacy surface.
1. Before sweeping `documents/`, `notes/`, `references/`, or local implementation directories, create or cite the `Structure Intake Packet` from `agents/COMMUNICATION_PROTOCOL.md`. Use its structure-reading artifacts as the entrypoint for choosing owner, document, and implementation surfaces; promote exact prose excerpts only after the packet shows they affect the next decision.
1. Preserve the user's requested scope before deriving work packets. Record `requested_scope` from the request clauses, then derive `work_scope` from owner boundaries, dependency evidence, and validation route. A bounded `work_scope` is allowed only as an implementation phase with explicit `covered_surfaces`, `deferred_surfaces`, and `omitted_surfaces` evidence; it is not completion evidence for a broader request.
1. Keep sweeps and cause investigations tied to the next concrete work. Each result updates one of: implementation route, reuse decision, stale-surface repair, dependency scope, validation route, durable issue, or explicit deferred owner. Evidence that leaves those fields unchanged stays as a short citation in the packet, then control returns to the current step.
1. Keep validation centered on static/read evidence. Use static analysis,
   dependency checks, docs checks, route checks, source/contract reading, and
   changed-file targeted tests as the primary validation evidence. Treat
   operation checks, smoke runs, full CI, long test suites, benchmarks,
   experiments, GPU / CPU numerical runs, solver sweeps, and randomized large
   cases as supplemental evidence only when changed runtime behavior,
   integration risk, or unresolved static findings require them. Record what
   the static/read evidence left unresolved before scheduling broader
   execution.
1. Before touching files, record a provisional workflow route from `agents/TASK_WORKFLOWS.md` and keep it revisable until owner boundary, replaceable unit, validation route, and public behavior / schema impact are evidenced.
1. In the first work update, declare `workflow=<provisional-or-final-family>`, `skills=<...>`, `review=<...>` with `$agent-orchestration` first in the skill list, and present apparent breadth only as provisional routing context.
1. When skills are explicitly named in the task or handoff, use `$skill-name` notation and preserve it in `skills=<...>`.
1. Treat `run.repo_tool_routing_policy` from `task_start.py` or `bootstrap_agent_run.py` as the selected repo-owned tool route. Carry `tool_route`, `tool_commands`, and `tool_evidence` into subagent handoff packets, and run each selected skill packet in the manifest order before replacing it with prose review.
1. For repo-changing edits, existing tool execution and owner-bounded patching
   proceed from tool-owned evidence. Runtime `SKILL.md` reading is optional
   follow-up context after the existing tool or selected command packet runs for
   the covered property. Read only the owner surface needed to interpret or
   repair the tool result. Route owner-bounded edits through
   `$owner-bounded-routing` and record owner, existing-tool route, and
   targeted-validation evidence.
1. For research-backed implementation, benchmark, external-research change,
   prior-art adoption, official-docs method claims, or literature-derived design
   decisions, the emitted `skills=...` / run-bundle skill call sequence calls
   `$literature-survey` before `$research-workflow`, before design, and before
   implementation. Carry the durable source packet into the
   `Implementation Source Packet` with source class, limitation, contrary or
   narrowing evidence, and adoption/exclusion decisions. Implementation,
   benchmark, report, and owner-bounded follow-up branches may not close a
   literature-backed claim from transient browser context or post-hoc citation
   cleanup.
1. ユーザー向けの作業更新、最終報告、レビュー要約、handoff guidance、reader-facing docs は日本語で書く。内部の field name、enum value、role key、helper 風の語は、command、path、table、正確な evidence reference に閉じる。専門語が必要な場合は、既存の repository term または外部標準 term を使い、自然文で説明する。
1. During requirements, resolve avoidable ambiguity from notes, guardrails, documents, prior logs, and local code or tests before asking the user; record the sweep and evidence in `user_request_contract.md`.
1. Keep `unknown_or_open_question` out of active must-do, must-not-do, and completion-evidence clauses; move remaining unknowns to deferred or escalation entries after the sweep.
1. For repo-changing implementation / patch / doc-edit work, bootstrap or schedule a selected write-capable implementer only when a separate writer is needed. Reuse a compatible active agent for revised scope; independent review, disjoint write authority, incompatible owner/context, or failed context integrity require a fresh agent. Plan, detailed-design, and document-flow reviewers are selected only when an owner-critical validation or unresolved branch activates them. Routine docs and Focused code still use targeted validation, and parent-direct edits follow the recorded exception route when required.
1. If the user explicitly asks for subagent coding/implementation/patch/editing, route completion through the selected write-capable implementer after the pre-handoff investigation packet derives dependency-expanded handoff scope, validation route, and `tool_rejection_preflight` evidence from route seed, responsibility search, reuse survey, and stale-surface scan.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Before detailed design selects implementation paths, write or cite an abstract design frame: responsibility model, concept graph or layer model, non-goals, future extension layers, evaluation axes, and canonical-surface relationships. Implementation scope, file list, and validation must be derived from that frame rather than from the nearest editable path or current finding alone.
1. Before implementation path selection, run or cite `python3 tools/agent_tools/search.py --query-file <request-or-design-question.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json` unless the approved design packet already fixes the owner, canonical paths, forbidden paths, and required checks. Use its bounded candidate paths as a source-packet seed, then confirm owner and edit scope with responsibility and dependency evidence before patching. A failed deterministic search transitions path selection to `router_unavailable_blocker`; continuation requires owner, responsibility, and dependency evidence naming one canonical route. Continuation also requires local/tool blocker evidence, including `selected_agent_type`, `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and `status=blocked`; canonical rerun continuation uses `canonical_rerun_pass`, `durable_blocker_or_issue`, or `explicit_approval_evidence` as durable exit markers.
1. After timeout, record the current status and return control. A later wait starts only with new state evidence or an explicit revised parent packet.
1. Before edits, create or cite the protocol-owned `Pre-Edit Repository Investigation Packet` from `agents/COMMUNICATION_PROTOCOL.md`. If this packet is missing or shallow, return to investigation before patching.
1. Close the `Pre-Edit Repository Investigation Packet` by naming the next concrete step and one owner. Continue with that step before opening another line of exploration.
1. Close the validation route by stating the static/read evidence used as the
   primary confirmation, whether broader execution is supplemental and
   approved, and the owner. Use static-only validation for policy, docs,
   metadata, contract-only wrappers, and checker-owned properties.
1. If a validation test or check fails, keep implementation intent, intended
   behavior, tests, slice contents, oracle strength, and validation scope stable
   until the packet records `failing_contract`, `observation_level`,
   `cause_classification`, `intent_preservation`, and `evidence`. Use
   `intent_preservation` for the same-intent repair or escalation route.
   Preserve approved intent for implementation bugs; repair test/design
   evidence for oracle or spec mismatches; route fixture, environment, or stale
   generated artifact failures to their owner; record unrelated failures as
   residual; escalate approved-design/user-request conflicts before changing
   intent.
1. Before commit or push, satisfy the `documents/operations/BRANCH_SCOPE.md` commit correctness contract and scope-split contract: treat the commit as the runnable Git unit and the PR as the review unit; include every validation-read source/config/schema/fixture/doc/tool entrypoint in the tracked tree; when a diff spans multiple problems, canonical owners, behavior or contract deltas, or validation routes, write a scope table and split independently landable slices into separate PRs or commits before merge; for code changes record file-level code dependency plus function/public-entrypoint call-site evidence when language tools support it; and record branch, commit SHA, submodule SHA, validation commands, validation paths, and any remaining dirty or untracked path classification.
1. Load the extra skills required by the current stage and contract; carry unrelated skills as deferred route signals. Nontrivial document creation or revision adds `prose-reasoning-graph` as the common graph/DSL gate and `$structure-planning` as the structure contract gate, then file/document responsibility selects the DSL-to-prose adapter: general explanatory README/workflow/guide/migration/spec docs add `long-form-writing`, submission papers or thesis-chapter drafts add `paper-writing`, broader academic or scholarly-note writing adds `academic-writing`, and the required notation/logic/citation reviewers follow that adapter choice. For typo/link/format-only edits, pair `$md-style-check` with `structure_contract=skipped` and the reason.
1. When the evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior / schema expansion, or when the work is Routine docs, Focused code, or typo/link/format-only, add `$owner-bounded-routing` before patching and keep targeted validation as the closeout route. File count is only auxiliary context.
1. If coordination, resumption, or selected specialist roles need durable
   lifecycle evidence, bootstrap `reports/agents/<run-id>/`; otherwise a
   semantically complete structured handoff is sufficient.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Before implementation, close the Design Integrity Gate: the `Abstract Design Frame` or parent-direct design-boundary note must name the responsibility model, replaceable unit, non-goals, and validation route before file-level work starts. Missing API shape, responsibility boundary, path layout, naming, algorithm, test oracle, dependency direction, runtime contract, or config-surface decisions are `design_issue_blocker` findings, not implementation latitude.
1. Before implementation, read the approved `design_brief.md` `Abstract Design Frame`, `Implementation Source Packet`, `Design Side-Effect Map`, and `Design-To-Implementation Trace`; confirm each implementation slice and downstream side effect is derived from the abstract responsibility model before citing the design artifact path, design section, test-plan item, and user-request clause IDs.
1. If implementation exposes a design issue, record `design_issue_blocker=<issue>` plus evidence and return to detailed design / design review. API shape, responsibility boundary, path layout, naming, algorithm, theorem target, test oracle, dependency direction, runtime contract, and config-surface gaps resolve through design review, with local fallback, wrappers, helpers, branches, compatibility routes, test relaxation, and docs overwrite treated as out-of-scope routes.
1. Close each implementation slice as a contract-complete implementation. Link the request clause, acceptance contract, `Implementation Source Packet`, and validation route; if the work would shrink the requested behavior into an implementation shortcut, record `design_issue_blocker=<issue>` plus evidence and return to design review.
1. Treat apparent breadth, `Owner-Bounded Change`, MVP, and thin slice labels as provisional routing, wave, and validation-profile signals. Implementation behavior is derived from the request clauses, acceptance contract, implementation source packet, design trace, dependency-expanded scope, validation route, and review gate. Revise the route when those sources show a different owner boundary or impact surface.
1. Only typo, formatting, import, and bounded mechanical follow-through that is uniquely determined by the approved design, local precedent, and existing responsibility boundary may be fixed in the same implementation pass. Anything requiring judgment is a design issue.
1. For implementation slices that touch classes, dataclasses, `Protocol`, inheritance, public API, type boundaries, or dependency direction, route `$oop-readability-check` into validation and carry SOLID principle signal counts, OOP dimension, finding kind, and the `tools/oop/shared/readability_core.py` mapping into the design artifact.
1. For SOLID-sensitive Python slices, validate evidence coverage with `python3 tools/agent_tools/check_solid_evidence.py --changed --evidence <oop-readability-report>` so the OOP readability report covers the changed path through `scanned_paths`.
1. Before implementation, read the approved `Dependency Manifest Plan`; load upstream dependency targets before editing and downstream targets after editing.
1. For new or edited human-authored text files, use the current `@dependency-start` / `@dependency-end` manifest format.
1. If the design trace is missing or conflicts with repo docs or code, return to detailed design review instead of editing from chat context.
1. Before parent-direct edits or write-capable subagent edits, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and put predicted OOP, helper, dependency, responsibility_scope, hook runtime, skill mirror, tool catalog, protocol, and log-surface gates plus repair commands into the work log or handoff. Record the owner scope and protecting tools before selecting the implementation directory.
1. For fresh subagent launches, include the protocol-owned `Fresh Subagent Context Capsule` from `agents/COMMUNICATION_PROTOCOL.md` instead of chat history, full transcripts, raw logs, full dashboards, or repo-root scope.
1. If runtime/tool gates block write-capable spawn, record local/tool evidence with `WRITE_SUBAGENT_AUTHORIZATION=required` or the specific gate blocker, `selected_agent_type`, `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and `status=blocked`; a different implementation route requires an explicit revised parent packet.
1. When implementation is driven by tool/checker/hook/reviewer/subagent findings, use `$tool-finding-report` first and pass the finding packet path, structured findings, impact, and prompt feedback decision into the parent or write-capable subagent handoff.
1. If `$tool-finding-report` classifies feedback as `handoff_prompt_gap` or `shared_skill_or_workflow_gap`, repair the handoff prompt, skill, workflow, or task catalog prompt before launching the next write-capable subagent.
1. Require `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker`; `worker` is the default. Use `spark_worker` only for a low-risk slice selected through `--select-agent-type implementer=spark_worker:<evidence>` and recorded in stdout / manifest. If the selected candidate is blocked, record `selected_agent_type`, `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and `status=blocked`; changing candidates requires a revised parent packet and wave.
1. Treat chunks, slices, checkpoints, and subpasses as internal progress only; continue until all planned work units, active clauses, selected review gates, validation, closeout gate, commit, and push are complete. A final review is included only when activated by the touched contract.
1. Validate dependency manifests with `python3 tools/agent_tools/check_dependency_headers.py --changed`, `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing`, and `bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header` before closeout.
1. If dependency edges changed, run `bash tools/agent_tools/check_dependency_graph.sh --print-edges` or record the migration baseline and evidence that the current diff introduced no new graph error.
1. Run `python3 tools/agent_tools/check_convention_compliance.py` before closeout for Shared canon, Large delivery, high-risk, or workflow/tooling changes so workflow readiness, convention tool gates, and skill-routing hooks are verified by the tool instead of repeated in prompt prose.
1. Validate with the static/read route first. Broader execution uses the
   task-linked approval note and records the static or reading signal that
   remained unresolved.
