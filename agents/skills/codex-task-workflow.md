# codex-task-workflow

<!--
@dependency-start
contract skill
responsibility Documents codex-task-workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit investigation and context capsule handoff packets
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest requirements
upstream design ../../documents/BRANCH_SCOPE.md defines Git commit correctness and push evidence
upstream design tool-finding-report.md tool-based finding packet and prompt feedback workflow
downstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

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

## Stages

1. intake
1. required context and library sweep
1. workflow selection
1. artifact placement
1. explicit subagent bootstrap
1. execution plan and plan review for full staged routes
1. detailed design and detailed design review for full staged routes
1. document flow review for reader-facing docs, new terms, public APIs, or full staged routes
1. implementation
1. validation
1. closeout

## Required Output

- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- `task_start.py` / `bootstrap_agent_run.py` が出す `REPO_TOOL_ROUTING_SEQUENCE`、
  `REPO_TOOL_ROUTING_NEXT_COMMAND`、`REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` を
  run-local packet として扱い、`team_manifest.yaml` の
  `run.repo_tool_routing_policy` を handoff に渡す
- Shared canon / Large delivery / high-risk / multi-step task では `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
- owner-bounded route では boundary-evidenced local route を使い、document-flow / broad design review は escalation 条件がある場合だけ起動する
- repo-changing implementation / patch / doc-edit work では、実装前に
  write-capable `spark_worker` / `worker` handoff を bootstrap または schedule
  する。Routine docs / Focused code でも targeted validation は使うが、
  parent-direct repo edit は `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` と
  `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` を
  記録した場合だけ使う
- repo-changing execution の編集では、既存 tool の実行や owner-bounded patching の前提として runtime `SKILL.md` 読了を要求しません。対象 property を正本として持つ既存 tool または command packet を先に使い、結果の解釈や修正に必要な owner surface だけを開きます。owner boundary、差し替え可能な単位、targeted validation route、public impact boundary が evidence で閉じた修正は `$owner-bounded-routing` に流し、owner boundary、existing-tool route、targeted validation を evidence に残す。外形的な作業量や file 数だけでは route を固定しません。実装 behavior は契約完全実装ポリシーから導く
- research-backed implementation、benchmark、external research、prior art、
  公式 docs、文献由来の design decision によって code、protocol、report claim、
  design を変える場合は、`skills=...` / run bundle の skill call sequence で
  `literature-survey` を `research-workflow`、設計、implementation より先に
  呼びます。durable source packet、source class、
  limitation、contrary / narrowing evidence、adoption/exclusion decision を
  `Implementation Source Packet` に接続し、post-hoc citation cleanup や一時的な
  browser context から実装 claim を閉じません。
- ユーザーが coding / implementation / patch / editing を明示的に依頼した場合は、read-only wave を completion ルートにしない。要件整理、surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation route、`tool_rejection_preflight` evidence から dependency-expanded handoff scope を作り、`spark_worker` / `worker` を起動してから実装へ進む
- repo-changing implementation / patch / doc-edit task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` を併用して write-capable `spark_worker` / `worker` handoff を既定 route にする。parent-direct は明示承認または subagent spawn / tool gate blocker を記録した例外 route としてだけ使う
- workflow family、public skill set、review stack は `agent-orchestration` の出力を入力として受け取り、この skill で routing matrix を重複定義しない
- ユーザー向けの作業報告、最終報告、レビュー要約、handoff guidance、reader-facing docs は日本語で書きます。内部の項目名、列挙値、役割名、補助関数風の語は、コマンド、パス、表、正確な根拠の引用に閉じます。専門語が必要な場合は、既存のリポジトリ用語または外部標準の用語を使い、自然文で説明します。
- AgentCanon update surface が repairable なら `make agent-canon-ensure-latest` を実行する。submodule repo では親 repo の無関係な dirty state はこの実行を block しない。update surface 自体が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon PR / proposal merge 後に `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰る
- AgentCanon source、submodule pin、`.gitmodules`、AgentCanon-owned root
  runtime view、root-copy surface、または parent root sync を変更した場合は
  `agentcanon_structure_followup=required` を記録する。template / derived
  parent root で `bash tools/sync_agent_canon.sh link-root` と
  `bash tools/sync_agent_canon.sh check` が pass した後にだけ
  `agentcanon_structure_followup=pass` を記録して closeout evidence に使う。
- commit / push の前に `documents/BRANCH_SCOPE.md` の commit correctness contract と範囲分割契約を満たす。commit は Git 上の実行単位、PR はレビュー単位として扱い、validation が参照した source、config、schema、fixture、文書、tool entrypoint を tracked tree に含める。複数の問題、canonical owner、behavior or contract delta、validation route にまたがる差分は範囲表を作り、merge 前に別 PR または別 commit へ分ける。code 変更では file-level code dependency と関数 / public entrypoint 単位の call-site evidence も残す。evidence には branch、commit SHA、submodule SHA、validation command、対象 path、残った dirty / untracked path の分類を残す
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
- 実装 path を選ぶ前に、承認済み design packet が owner、canonical paths、forbidden paths、required checks をすでに固定していない限り、`agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text` を走らせるか引用する。code、tool、skill、workflow、document、runtime instruction のどこに置くかは、この structured route を source packet seed にして決める。LocalLLM が無い場合は deterministic fallback の `PRIMARY_PATHS` / `FORBIDDEN_PATHS` を provisional source-packet seed として使うか `router_unavailable_blocker` として記録し、responsibility search と dependency scope で owner と edit scope を確定する。fallback routing は `fallback_exit_status` として `canonical_rerun_pass`、`durable_blocker_or_issue`、`explicit_approval_evidence` のいずれかに接続する
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
- 実装前に `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら Abstract Design Frame と design trace から導かれた bounded slice は `spark_worker` を使い、design interpretation / conflict resolution / broad architecture judgment / scope judgment を含む slice は `worker` を使う
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- parent 直編集でも write-capable subagent でも、実装前に cause investigation artifact を固定し、`Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残してから code edit に入る
- parent 直編集でも write-capable subagent でも、実装前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、予測された cause investigation / OOP / helper / dependency / responsibility_scope / hook runtime / skill mirror / tool catalog / protocol / log-surface gate と repair plan を handoff または work log に残す。実装ディレクトリを選ぶ前に owner scope と protecting tools を記録する
- fresh subagent に渡す prompt は chat history 依存にしない。`agents/COMMUNICATION_PROTOCOL.md` が定義する `Fresh Subagent Context Capsule` を渡し、full transcript、raw logs、full dashboard、repo root 全体を context として渡さない
- runtime/tool gate が write-capable spawn を阻害する場合は `WRITE_SUBAGENT_AUTHORIZATION=required` または該当 gate blocker を記録し、slice を `fallback_exit_status` に接続する。継続 route は canonical gate rerun による `canonical_rerun_pass`、`durable_blocker_or_issue`、または `explicit_approval_evidence` 付き revised workflow route とする
- tool / checker / hook / reviewer / subagent feedback から実装へ入る場合は `tool-finding-report` で finding packet を作り、write-capable subagent handoff に artifact path、structured findings、prompt feedback decision を渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` が出た場合は、次の write-capable subagent を起動する前に handoff prompt、skill、workflow、または task catalog prompt を修正する
- prompt/config drift が shared canon surface をまたぐ場合は、親がその場で prose を増やす前に `prompt_config_reviewer` で audit し、この workflow はその監査結果と契約から導かれる差分を適用する
- nontrivial document creation / revision では `prose-reasoning-graph` と `structure-planning` を構造先行 gate として通し、その後に `long-form-writing` / `paper-writing` / `academic-writing` へ渡す。typo / link / format-only では `md-style-check` と `structure_contract=skipped` の理由を evidence に残す
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
- Shared canon / Large delivery / high-risk / workflow-tooling change では closeout 前に `python3 tools/agent_tools/check_convention_compliance.py` を通し、workflow prohibition、convention tool gate、skill-routing hook の欠落を tool で検出する
- 検証は該当する範囲で静的解析・読み取り route から始めます。広い実行は
  実行前の確認記録を使い、静的解析・読み取りで残った未確認点を記録します。
