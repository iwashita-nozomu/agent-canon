<!--
@dependency-start
contract workflow
responsibility Documents 実装ウォーターフォールワークフロー for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines canonical Codex task gates
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest gates
downstream design ../templates/closeout_gate.md records closeout evidence required by this workflow
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py verifies design-doc evidence claims
@dependency-end
-->

# 実装ウォーターフォールワークフロー

この文書は、repo に変更を入れる実装プロセスを、段階ゲート付きのウォーターフォールとして進めるための正本です。
対象は `python/`、`documents/`、`agents/`、`docker/`、`scripts/` など、repo に持ち帰る変更全般です。

この repo では workflow family の選択は `agents/TASK_WORKFLOWS.md` を使いますが、実装そのものの進め方はこの文書を共通ルールにします。
README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書では、加えて `agents/workflows/long-form-writing-workflow.md` を overlay として使います。
論文、thesis chapter、scholarly note のような学術文章では、`agents/workflows/academic-writing-workflow.md` を優先 overlay として使います。
原因考察、修正箇所選定、複数候補比較が必要な変更では、`agents/workflows/hypothesis-validation-workflow.md` を overlay として使います。

## この文書の読み方

- この文書は、repo に持ち帰る code / docs / environment change の実装 gate を所有します。
- 前半は目的、適用範囲、標準ゲート、反復 cycle を固定し、後半は差し戻し、prototype、family 別 route、reuse-first、closeout、convention gate を扱います。
- 実装担当者は `## 4. 標準ゲート` と `## 4A. 反復サイクル` から読み、reviewer は差し戻しと closeout の節を合わせて確認します。
- chunked reading では、まずこの map と `## 4. 標準ゲート` を読み、必要な overlay だけを `## 7. Family ごとの使い分け` から辿ります。

## 1. 目的

- stage ごとに適切な subagent / specialist を explicit に立てる
- context sweep と library sweep を済ませる前に stage を始めない
- 要件が固まる前に code を書き始めない
- 計画が固まる前に詳細設計へ進まない
- 詳細設計が固まる前に実装を広げない
- 実装は承認済みの設計文書 packet を読んでから始める
- 設計文書と実装の正本を 1 本に固定し、tracked tree に parallel truth を残さない
- 実装、review、verification を段階ゲートで区切る
- 各 pass で複数回の独立レビューを必須にする
- `設計 -> レビュー`、`詳細設計 -> レビュー`、`実装 -> レビュー` を完了条件充足まで反復する
- 変更要求 1 件につき 1 回の実装パスを閉じる
- 差し戻しが必要な場合は、どの段へ戻すかを明示する
- 新規実装より前に、既存コードと既存の書き方を徹底的に再利用する
- 考察系 task では、code dependency と header dependency を別 tool で抜き、仮説と修正箇所妥当性を固定してから実装する

## 2. 文献ベースの判断

この workflow は、純粋な無反復 waterfall ではなく、初期段階だけ限定的に戻りを許す phase-gated waterfall として定義します。

- Royce 1970:
  - 要件、分析、設計、実装、試験を段階化しつつ、設計先行、文書化、pilot model、test planning を強く要求しています。
  - 同時に、単純な一方向実装は risky だと明言しており、初期段階での制御された戻りを前提にします。
- NASA Systems Engineering Handbook Rev 2:
  - stakeholder expectations、technical requirements、logical decomposition、design solution、implementation、integration、verification、validation、transition を別プロセスとして扱います。
  - life-cycle review と technical review を decision gate として扱う考え方を採用します。
- NIST SP 800-218 / 800-218A:
  - secure software development practice は特定手法に依存せず、各 SDLC 実装へ統合すべきとしています。
  - そのため、この repo の waterfall でも security、provenance、AI 特有のリスク確認を verification gate に埋め込みます。

## 3. 適用範囲

- `Scoped Change`
- `Large Delivery`
- `Platform And Environment`
- `Comprehensive Development`
- `Research-Driven Change` のうち、repo へ持ち帰る各 code/doc/environment change

研究や実験の outer loop 自体は反復して構いません。ただし、1 回の change request を repo に入れる実装パスは、この文書の gate を順に通します。
言い換えると、研究は複数回の waterfall pass を並べて進め、1 pass の途中で要件や設計を曖昧なまま変形させません。

## 4. 標準ゲート

この workflow では、契約完全性を満たす標準 stage として次を順に通します。

1. subagent bootstrap
1. 要件整理
1. 調査
1. 実行計画立案
1. 計画レビュー
1. 詳細設計
1. 詳細設計レビュー
1. 文書通読レビュー
1. テストケース設計（behavior-changing / regression-prone / high-risk の場合）
1. 実装
1. 実装 checkpoint review
1. 最終受け入れ review
1. audit / gate close

`Scoped Change` のような bounded 差分でも、実行計画、計画レビュー、詳細設計、詳細設計レビューを省略しません。
文書通読レビューは reader-facing docs、新用語、公開 API、workflow surface がある場合の active gate として扱います。
また、`計画レビュー`、`詳細設計レビュー`、active な `文書通読レビュー` は別エージェントで行います。とくに `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします。
behavior-changing、regression-prone、または high-risk code pass では、実装前に
`test_designer` を独立に立て、static path と nasty case を test plan として固定します。
`cause_classification=implementation_bug` の validation failure は、
`failing_contract`、`observation_level`、`cause_classification`、
`intent_preservation`、`evidence` を記録した後、追加 test planning で止めずに
owning implementation repair へ進めます。
contract-only wrapper pass では、static contract validation と canonical checker command を validation evidence にします。
この gate 順は implementation sequence です。独立 workstream が複数ある場合、parent は同じ sequence を workstream ごとの stage owner に割り当て、evidence と review gate に応じて vertical dynamic wave を追加します。

## 4A. 反復サイクル

この workflow は gate を 1 回通過して終わりではありません。次の 3 つの cycle を持ち、各 cycle は review decision が `approve` になるまで反復します。
次段へ進む前の機械チェックは次を使います。

```bash
make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <requirements|plan|design|document_flow|test|implementation|final>"
```

`WATERFALL_GATE_READY=no` の場合は、`NEXT_ACTION` に出た owner stage へ戻し、空テンプレート、未承認 review、未記入 artifact を直してから再実行します。

### Cycle A. 実行計画 -> 計画レビュー

- 対象:
  - Gate 3 実行計画立案
  - Gate 4 計画レビュー
- owner:
  - `scheduler`
- reviewer:
  - `schedule_reviewer`
- 反復規則:
  - `schedule_review.md` の decision が `approve` でない限り Gate 3 に戻します
  - `revise` は Gate 3 へ戻します
  - `escalate` は Gate 1 または Gate 2 へ戻して scope / research を修正します
- 完了条件:
  - stage 順序、handoff、rollback、validation sequence が hidden step なしで実行できる
  - review 分離と parent-managed write-scope discipline が崩れていない

### Cycle B. 詳細設計 -> 設計そのもののレビュー -> 文書通読レビュー

- 対象:
  - Gate 5 詳細設計
  - Gate 6 詳細設計レビュー
  - Gate 7 文書通読レビュー
- owner:
  - `designer`
- reviewers:
  - `design_reviewer`
  - active gate の場合は `document_flow_reviewer`
- 反復規則:
  - Gate 5 で詳細設計を作成した直後に Gate 6 を通します。設計文書は
    書かれただけでは承認済みではありません
  - Gate 6 は実装 diff ではなく、Gate 5 で作られた同一の詳細設計文書
    そのものを review 対象にし、`design_review.md` に design artifact path
    と対象 revision / section を記録します
  - `design_review.md` の decision が `approve` でない限り Gate 5 に戻します
  - 文書通読レビューが active gate の場合は、`document_flow_review.md` の decision が `approve` でない限り Gate 5 に戻します
  - `revise` は Gate 5 へ戻します
  - `escalate` は Gate 3 へ戻して設計方針を組み替えます
- 完了条件:
- 実装者が文書だけ読んで着手できる
- `Abstract Design Frame`、`Implementation Source Packet`、`Design-To-Implementation Trace` が揃っている
- `Evidence And Assumption Ledger` が current code、dependency header evidence、parent documents、初出 DSL / standard-form terms を設計 claim に接続している
- 新規または変更された design document は、詳細設計レビュー前に次の gate を通している
  `python3 tools/agent_tools/check_design_doc_claims.py --root . <design-doc>`
- `Canonical Tree-Head Plan` が、正本として残す設計文書 path / 実装 path と削除対象の non-canonical path を明示している
- reuse-first、style-following、reader path が blocker なしで揃っている

### Cycle C. 実装 -> 実装 checkpoint review

- 対象:
  - Gate 8 実装
  - Gate 8 内の実装 checkpoint review
- owner:
  - `implementer`
- reviewer:
  - `change_reviewer`
- 反復規則:
  - `change_review.md` の decision が `approve` でない限り Gate 8 に戻します
  - `revise` は Gate 8 へ戻します
  - `revise`、`required_change`、または rejected slice への応答は、同じ
    request clause と approved design intent を保つ修正として行います
  - `escalate` は Gate 5 へ戻して詳細設計か test plan を修正します
- 完了条件:
- diff が approved design と test plan に一致する
- 各実装 slice が design artifact、design section、test plan item、request clause ID を引用している
- tracked tree に non-canonical design doc、implementation copy、snapshot、backup path を増やしていない
- regression、style drift、stale path、missing test が blocker なしになる

### Gate 0. Subagent Bootstrap

目的:
- run bundle と review artifact を先に固定する
- 要件 reviewer、計画 reviewer、詳細設計 reviewer、文書通読 reviewer を別 agent instance として割り当てる

最低限の記録:
- `team_manifest.yaml`
- `intent_brief.md`
- `user_request_contract.md`
- `schedule.md`
- `work_log.md`
- `decision_log.md`

条件付き追加 subagent:
- repo 内調査が要る場合は `explorer`
- 文書主体の整理が要る場合は `docs_workflow_steward`

必須ルール:
- Gate 0 の前に `documents/`、`notes/`、`references/` と local library の sweep を済ませます
- Gate 0 の前に `user_request_contract.md` へ must-do、must-not-do、completion-evidence clause を書きます
- Gate 0 の直後から `schedule.md` を task TODO の正本として更新し、repo-changing task では `work_log.md` を kickoff から closeout まで残します
- repo-changing task では explicit subagent activation を省略しません
- active runtime が explicit user request なしの subagent spawn を禁止する場合は、actual spawn の代わりに `SUBAGENT_AUTHORIZATION=required`、role、input packet、expected output、review gate を run bundle に固定し、許可が出るまでその specialist review を完了扱いにしません
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別 agent instance で行います
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします
- 包括的開発では、parent が writer ごとの path / directory を `team_manifest.yaml` の write policy で管理します
- 包括的開発では、same directory / same public API surface の parallel write を許可しません
- 独立 workstream が複数ある場合は、同じ parent wave に全 role を詰めず、stage owner ごとの vertical dynamic wave として schedule / workflow monitoring に記録します

### Gate 1. 要件整理

目的:
- 変更要求を 1 件に固定する
- 影響範囲、非対象、受け入れ条件を固定する

最低限の記録:
- `Change Request:`
- `Scope:`
- `Non-Goals:`
- `Acceptance Criteria:`
- `Validation Plan:`
- `User Request Clause IDs:`
- `Requirement Source Buckets:`
- `Requirements Resolution Sweep:`
- `Resolved From Accumulated Context:`
- `Unknowns And Open Questions:`

主担当:
- `manager`
- `manager_reviewer`

条件付き追加 subagent:
- repo survey が要る場合は `explorer`

必須レビュー:
- `manager_reviewer`
  - scope、non-goals、acceptance criteria、validation plan の粗さを確認する
  - 各 clause の source bucket が妥当か確認する
  - notes、guardrails、knowledge、failures、documents、prior logs、local code / tests の sweep で解決できる unknown が残っていないか確認する
  - active clause に `unknown_or_open_question` が混ざっていないか確認する
  - 過去ログ由来の user trait が、今回 task の requirement に混入していないか確認する
  - family 選択が妥当か確認する

source bucket:
- `current_request`
  - 今回の user request に明示された requirement
- `durable_user_preference`
  - `memory/USER_PREFERENCES.md` や過去ログから抽出された user tendency
- `repo_or_code_precedent`
  - 既存 code、test、docs、workflow から分かる制約
- `domain_or_external_constraint`
  - 外部仕様、論文、API、runtime、法規制などから来る制約
- `unknown_or_open_question`
  - まだ決められない項目。silent assumption にせず deferred / escalated にする

ルール:
- 不明点はすぐユーザーへ戻さず、まず `documents/`、`memory/`、`notes/themes/`、`notes/guardrails/`、`notes/knowledge/`、`notes/failures/`、prior logs、local code / tests から解決を試みます
- 蓄積情報で user intent、scope、acceptance criteria を変えずに解決できる場合は、evidence path とともに `Resolved From Accumulated Context` へ記録します
- durable user preference は、今回の request や repo evidence と結び付いたときだけ task requirement に昇格します
- unknown は requirement として採用せず、resolution sweep 後に open question、deferred clause、または escalation として残します
- active な must-do、must-not-do、completion-evidence clause には `unknown_or_open_question` を使いません
- 変数名、関数名、class 名、file 名、CLI flag、config key、public API identifier は、user request または repo precedent が固定している場合だけ Gate 1 で固定します
- naming が未確定の場合は worker の裁量にせず、Gate 5 の identifier naming plan で扱う open decision にします

exit 条件:
- 何をもって完了とするかが 1 文で言える
- どの family で扱うかが決まっている
- 実装前に必要な review / validation が決まっている
- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言している
- すべての clause が source bucket を持ち、unknown が silent assumption になっていない
- 解決可能な unknown を accumulated context で解決し、残った unknown は deferred / escalated へ移している
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate requirements"` が pass している
- requirements review が `resolved` になっている

### Gate 2. 調査

目的:
- 既存コード、既存 docs、外部根拠、既存 implementation pattern を調べる

主担当:
- 必要に応じて `researcher`
- 必要に応じて `research_reviewer`

条件付き追加 subagent:
- 外部文献が要る場合は `literature_researcher`
- repo 内の precedent 調査は `explorer`

最低限の記録:
- `Existing Code To Reuse:`
- `Existing Writing Style To Follow:`
- `Prior Art Or Local Precedent:`
- `Research Gaps:`

exit 条件:
- 何を再利用し、何を新規に足すかが言える
- 調査が必要な task では research review が `resolved` になっている

### Gate 3. 実行計画立案

目的:
- stage 順序、担当 agent、handoff、validation 順序を固定する

最低限の記録:
- `Stage Order:`
- `Owner Agent Per Stage:`
- `Review Agent Per Stage:`
- `Validation Sequence:`
- `Rollback Points:`

主担当:
- `scheduler`

条件付き追加 subagent:
- 文書主体なら `docs_workflow_steward`

必須レビュー:
- ここでは plan review は行いません。次 gate で独立 reviewer に渡します。

ルール:
- 実行計画は詳細設計の前に必ず確定させます
- どの subagent / role がどの stage を担当するか明記します
- 包括的開発では、`Write Scope Ledger:` と `Integration Order:` を書きます
- 複数 writer が必要な場合は、writer ごとの disjoint path と current checkout 内の wave 順序を明記します。separate worktree は使いません

exit 条件:
- `schedule.md` に stage 順序、担当 agent、exit criteria、validation が書かれている
- `schedule.md` に clause coverage が書かれている
- `schedule.md` の `Planned Work Units` が TODO として具体化されている
- 実装へ進む前に必要な review agent がすべて割り当てられている

### Gate 4. 計画レビュー

目的:
- 実行計画の順序、review 分離、rollback point を独立に確認する

最低限の記録:
- `Stage Risks:`
- `Reviewer Separation Risks:`
- `Rollback Gaps:`
- `Required Revisions:`

主担当:
- `schedule_reviewer`

条件付き追加 subagent:
- `reviewer`

必須レビュー:
- `schedule_reviewer`
  - stage 順序、依存関係、review agent の分離、rollback point を確認する
- 必要に応じて `infra_reviewer`
  - runtime、CI、Docker、dependency 影響が計画に反映されているか確認する

ルール:
- 計画レビュー agent を詳細設計レビュー agent と兼務させません
- stage の飛ばしや merge は認めません
- `schedule_review.md` の decision は `approve`、`revise`、`escalate` のいずれかに固定します
- `revise` または `escalate` のまま Gate 5 へ進みません

exit 条件:
- `schedule_review.md` が `resolved` になっている
- decision が `approve` になっている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate plan"` が pass している

### Gate 5. 詳細設計

目的:
- 実装前提を十分に伝える詳細設計文書を起こす
- 既存コードと既存の書き方をどう踏襲するかを明文化する

主担当:
- `designer`

条件付き追加 subagent:
- 文書主体なら `docs_workflow_steward`
- 既存 code path 調査が要る場合は `explorer`

最低限の記録:
- `Existing Code And Docs To Reuse:`
- `Upstream Requirement Packet:`
- `Abstract Design Frame:`
- `Implementation Source Packet:`
- `Installed Libraries And Existing Implementation Survey:`
- `Dependency Manifest Plan:`
- `Canonical Tree-Head Plan:`
- `Design Side-Effect Map:`
- `Patterns And Writing Style To Mirror:`
- `File-By-File Design:`
- `Design-To-Implementation Trace:`
- `Interfaces And Boundaries:`
- `Identifier And Naming Plan:`
- `Validation And Rollback Plan:`
- refactor pass では追加で `Behavior Contract:`, `Allowed Structural Delta:`, `Forbidden Semantic Delta:`, `Files To Remove Or Move:`, `Path Mapping:` を残します
- directory layout、directory README ownership、root view、または responsibility-scope map refactor では追加で `Directory Responsibility Map:`, `Recursive README Sources:`, `Scope Delta:`, `Reader Navigation Delta:`, `Scope Overlap Report:`, `Import Responsibility Report:` を残します
- 大規模 repo の包括 refactor では追加で `Current Responsibility Map:`, `Target Responsibility Map:`, `OOP Boundary Plan:`, `Refactor Surface Baseline:`, `Signal Class Outcome:`, `Accepted Warning Ledger:`, `Human Review Gate:`, `Static Analyzer Limits:` を残します

ルール:
- 詳細設計の目標は、実装前に読むべき文書を完成させることです
- Design Integrity Gate はこの gate の中心条件です。設計は
  owning responsibility model から始め、近い file、current finding、会話印象から
  file-level work を決めません。API shape、責務境界、path layout、命名、
  アルゴリズム、test oracle、依存方向、runtime contract、config surface の
  判断不足は `design_issue_blocker` として扱い、implementation shortcut に
  しません
- `Upstream Requirement Packet` には、designer が詳細設計前に読んだ `user_request_contract.md`、`schedule.md`、`intent_brief.md`、waterfall 正本、governing doc の path を列挙します
- `Abstract Design Frame` には、実装対象 file や直近 finding へ絞る前の抽象責務、概念 graph または layer model、非対象、将来拡張 layer、評価軸、既存正本との関係を列挙します。`File-By-File Design`、`Design-To-Implementation Trace`、validation はこの frame から導きます
- `Installed Libraries And Existing Implementation Survey` には、designer が見た dependency surface、導入済みライブラリ候補、既存実装候補、reuse / extend / replace / add-new の判断、既存では足りない理由を列挙します
- `Implementation Source Packet` には、worker が編集前に読む `user_request_contract.md`、`schedule.md`、`design_brief.md`、`design_review.md`、active な場合の `document_flow_review.md`、`test_plan.md`、repo docs、dependency surface、code path、test path、外部 reference を列挙します
- `Design Side-Effect Map` には、主要設計判断ごとに影響する implementation、document、workflow、prompt/config、validation、dependency manifest、user-facing surface を列挙し、各 item を `Abstract Design Frame`、request clause ID、reuse precedent、owner stage、review gate、validation / test-plan item に接続します
- `Dependency Manifest Plan` には、編集対象 file ごとに追加・維持する `upstream` / `downstream` edge、kind、相対 path、reason、編集前に読む upstream context、編集後に確認する downstream context を列挙します
- 新規・変更する human-authored text file では旧 `Dependency Files:` block を使わず、`documents/dependency-manifest-design.md` の `@dependency-start` / `@dependency-end` 形式に統一します
- 新しい dependency edge を足す場合は reverse edge も同じ pass の file plan に入れます。移行中で reverse edge 追加を同じ pass に含められない場合は、design review に blocker か明示 escalation として出します
- `Canonical Tree-Head Plan` では、task 完了後に tracked tree に残してよい canonical design path と canonical implementation path を固定し、parallel design doc、implementation copy、dated snapshot、backup file、duplicate directory を作らないことを明示します
- `bootstrap_agent_run.py` と `task_start.py` は `DESIGN_DOCUMENT_PACKET` と `IMPLEMENTATION_DOCUMENT_PACKET` を出力します。parent は designer / implementer subagent 起動時にその path 群をそのまま渡します
- `Design-To-Implementation Trace` には、各予定差分ごとに design section、request clause ID、source / reuse 文書または code path、test plan item、validation evidence を対応付けます
- 新規 helper、new module、new dependency、new public API を足す差分では、既存実装や導入済みライブラリでは足りない理由を `Design-To-Implementation Trace` に対応付けます
- 既存 module boundary、命名、API shape、test style、docs style から逸脱する場合は、理由を明示します
- 新規または rename する variable、function、class、file、CLI flag、config key、public API identifier は、既存 precedent、採用名、却下した代替案、review 観点を明記します
- 既存 precedent がある場合はそれを採用し、ない場合は理由を文書化して Gate 6 で確認します
- worker が naming、API shape、path layout、boundary choice を発明しなくてよい状態まで詳細設計を詰めます
- worker が会話文脈や記憶を実装入力にしなくてよい状態まで、必要な判断を設計文書内に再掲します
- worker が chat 要約ではなく packet path を実際に読めるよう、document packet は absolute path で明示します
- Gate 5 が詳細設計を作成したら、designer は実装や worker handoff へ進まず
  `design_review_required=yes` として Gate 6 に渡します
- refactor pass では semantic delta を feature 追加として混ぜません
- refactor pass では path mapping と remove list を実装前に固定します
- structure refactor では recursive directory README graph と dependency / responsibility-scope evidence から path mapping を作り、README 更新だけで構造矛盾を隠しません
- 包括 refactor では、必要に応じて `tools/agent_tools/analyze_refactor_surface.py` または task 固有解析 tool の score を design gate に入れます。score pass は behavior evidence の代替ではなく、責務境界の補助 evidence として扱います
- Gate 6 または Gate 7 が `revise` / `escalate` を返したら Gate 5 へ戻ります

exit 条件:
- 実装者が文書だけ読んで着手できる
- designer が upstream 文書だけ読んで詳細設計に着手できる
- worker が編集前に確認する抽象責務と、編集前に読む文書 / code path が `Abstract Design Frame` と `Implementation Source Packet` だけで分かる
- 実装対象 file、helper、current finding に絞る前の抽象責務と概念 model が `Abstract Design Frame` だけで分かる
- 設計判断の downstream side effect が `Design Side-Effect Map` から owner stage、review gate、validation route へ辿れる
- worker が編集前に読む upstream dependency context と、編集後に確認する downstream dependency context を `Dependency Manifest Plan` だけで分かる
- 各予定差分が `Design-To-Implementation Trace` で clause、source、test、validation へ結び付いている
- 新規 abstraction より reuse-first の方針が説明できる
- 新規または rename する identifier と path の naming plan が文書だけで追える
- refactor pass では move / rename / split と挙動保存境界が文書だけで追える
- 包括 refactor では設計見直し、OOP 的な契約完全実装方針、解析 baseline / signal class outcome / accepted-warning ledger / human review gate が文書だけで追える

### Gate 6. 詳細設計レビュー

目的:
- Gate 5 で作成された詳細設計文書そのものを、実装前に独立 review する
- 詳細設計文書の十分性と、reuse-first / style-following が担保されているか確認する

主担当:
- `design_reviewer`
- 必要に応じて `infra_reviewer`

条件付き追加 subagent:
- `reviewer`
- Python 差分が中心なら追加で `python_reviewer`
- C / C++ 差分が中心なら追加で `cpp_reviewer`
- repo-wide 影響が大きければ `project_reviewer`

必須レビュー:
- `design_reviewer`
  - `design_review.md` の `Design Artifact Under Review` に、対象の
    `design_brief.md` path、対象 revision / section、review した source packet
    を記録する
  - implementation diff、worker summary、または parent の会話要約ではなく、
    Gate 5 の詳細設計文書そのものを判定対象にする
  - 文書 completeness、実装可能性、既存コード再利用、既存の書き方踏襲、不要な新規性を確認する
  - `Abstract Design Frame` が実装対象 file、既存 helper、current finding より先に抽象責務、概念 model、非対象、将来 layer、評価軸、既存正本との関係を固定し、そこから実装 slice を導いているか確認する
  - `Installed Libraries And Existing Implementation Survey` が dependency surface、既存実装候補、reuse 判断、既存では足りない理由を列挙しているか確認する
  - `Implementation Source Packet` が編集前に読む artifact、repo docs、dependency surface、code path、test plan を列挙しているか確認する
  - `Design Side-Effect Map` が主要設計判断から downstream surface、owner stage、review gate、validation / test-plan item へ trace できるか確認する
  - `Dependency Manifest Plan` が各 touched file の `@dependency-start` block、upstream / downstream edge、reverse edge、読む順序、検証 command に落ちているか確認する
  - 旧 `Dependency Files:` block を新規・変更 file に残す設計を blocker として扱う
  - `Canonical Tree-Head Plan` が current tree head だけを durable state にし、non-canonical design / implementation path を排除しているか確認する
  - 各予定差分が design section、request clause ID、reuse/source 文書または code path、test plan item、validation evidence へ trace できるか確認する
  - worker が会話文脈や記憶を使わないと実装できない箇所を blocker として確認する
  - identifier naming plan が既存 precedent または明示 rationale に結び付いているか確認する
  - worker が reusable / user-facing な名前を発明する余地が残っていないか確認する
- 必要に応じて `infra_reviewer`
  - infra / runtime 影響が設計文書に落ちているか確認する
- `project_reviewer`
  - refactor pass では stale path、cross-module drift、delete 漏れを確認する

ルール:
- `詳細設計レビュー` は計画レビューより重い gate とします
- `design_review.md` の decision が `approve` になるまで、実装、worker
  handoff、implementation checkpoint review、または設計を前提にした
  follow-up task へ進みません
- 承認は latest design artifact にだけ有効です。Gate 5 で設計を修正したら、
  旧 `approve` を流用せず Gate 6 を再実行します
- design reviewer が未解消の懸念を残したまま実装へ進みません
- naming plan、API shape、path layout、boundary choice の不足は `revise` blocker とします
- `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、`Design Side-Effect Map`、または `Design-To-Implementation Trace` の不足は `revise` blocker とします
- `Dependency Manifest Plan` の不足、reverse edge 欠落、旧形式温存は `revise` blocker とします
- refactor pass では `project_reviewer` の stale path 指摘を未解消のまま実装へ進みません
- `design_review.md` の decision は `approve`、`revise`、`escalate` のいずれかに固定します

exit 条件:
- `design_review.md` が `resolved` になっている
- reuse-first と style-following の懸念が解消している
- implementation source packet と design-to-implementation trace の懸念が解消している
- abstract design frame と implementation slice の対応懸念が解消している
- dependency manifest plan と graph validation plan の懸念が解消している
- canonical tree-head plan の懸念が解消している
- naming plan の懸念が解消している
- decision が `approve` になっている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate design"` が pass している

### Gate 7. 文書通読レビュー

目的:
- 文書を上から順に読んだときに、最初の reader が意味を追えるか確認する

主担当:
- `document_flow_reviewer`

条件付き追加 subagent:
- `reviewer`
- 文書差分が大きいなら追加で `project_reviewer`

必須レビュー:
- `document_flow_reviewer`
  - section 順序、用語の先出し、前提の提示順、結論までの reader path を確認する
  - 「途中で前提が出る」「定義前の語が出る」「どこを読めば判断できるか分からない」を blocker として扱う

ルール:
- `document_flow_reviewer` は `design_reviewer` と兼務させません
- 文書主体の成果物では、top-down readthrough で major rewrite が必要なまま実装へ進みません

exit 条件:
- `document_flow_review.md` が `resolved` になっている
- 上から順に読んだときの意味の飛び、定義不足、section order の問題が解消している

### Gate 7.5. テストケース設計

目的:
- behavior-changing、regression-prone、high-risk、または oracle / spec risk がある場合に、実装前の static path、境界ケース、failure path、regression-prone case を test plan に落とす

主担当:
- `test_designer`

条件付き追加 subagent:
- `test_designer`
- 必要に応じて `explorer`

最低限の記録:
- `Static Path Survey:`
- `Nasty Cases:`
- `Regression Cases To Keep:`
- `Implementation Notes:`

ルール:
- `test_designer` は read-only とし、repo file は編集しません
- 既存 test style、fixture layout、naming を先に調べ、そこへ寄せます
- design や code path の静的解析から出る nasty case を曖昧な助言ではなく具体ケースとして残します
- `cause_classification=implementation_bug` と判断でき、contract と oracle が安定している場合は、Gate 7.5 を再度広げず Gate 8 の owning implementation repair へ戻します
- 実装者は test plan を読んで tests を同じ pass で落とし込みます

exit 条件:
- `test_plan.md` が作られている
- boundary case、malformed input、error path、state transition、regression case が明示されている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate test"` が pass している

### Gate 8. 実装

目的:
- 凍結済みの設計を実装へ落とす

主担当:
- write-capable Codex implementer selected from `IMPLEMENTATION_CODEX_AGENTS`
  (`spark_worker` for bounded low-risk slices, otherwise `worker`)
- parent is the gate owner / integrator only

条件付き追加 subagent:
- additional write-capable `spark_worker` / `worker` instances only when
  dependency order, disjoint write scope, integration order, and review gate are
  fixed in the handoff packet

ルール:
- Gate 8 starts from `IMPLEMENTATION_HANDOFF_REQUIRED=yes` and
  `PARENT_REPO_EDITS_ALLOWED=no`. The parent owns routing, handoff packet
  construction, monitoring, additional instructions, integration, validation,
  and closeout; it does not directly patch repository files unless
  `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` and
  `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` are
  recorded.
- Gate 8 cannot start from a detailed design until `pre_handoff_gate_status`
  records the current design artifact, `design_review.md decision=approve`, and
  `waterfall-gate-check --gate design` pass evidence.
- Parent-Direct Context Note is a routing / handoff artifact, not edit
  authorization. Once edit scope is known, launch or schedule `spark_worker` /
  `worker`; if blocked, record `WRITE_SUBAGENT_AUTHORIZATION=required` or
  `write_capable_handoff_blocker=<gate>` before any parent-direct exception.
- chunk、slice、checkpoint、subpass は内部進捗であり、user request 全体の完了ではありません
- 実装前に `Abstract Design Frame`、`Implementation Source Packet`、`Design Side-Effect Map` の全項目、`design_review.md`、active な場合の `document_flow_review.md`、`test_plan.md` を読み、抽象責務と概念 model から実装 slice が導かれていることを実装 summary に残します
- 実装前に `Dependency Manifest Plan` の upstream edge target を読み、編集後に downstream edge target を確認します
- 実装前に `Installed Libraries And Existing Implementation Survey` を読み、既存ライブラリ拡張か既存実装拡張か新規追加かの判断を実装 summary に残します
- 会話、記憶、直感を、承認済み設計文書より優先しません
- design artifact と現在の repo docs / code が矛盾する場合は、実装で解釈せず Gate 5-6 へ戻します
- 実装は 1 つの change request に閉じます
- docs と tests は同じ pass で更新します
- `test_plan.md` の nasty case を最低限どこへ落とし込んだか説明できるようにします
- 途中で scope を広げません
- 設計を変えたくなったら Gate 5-6 を開き直します
- 実装中に設計上の問題を見つけた場合は、勝手に実装で吸収せず `design_issue_blocker` と evidence を残して Gate 5-6 へ戻します。対象は API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾です。local fallback、wrapper、helper、分岐、互換 route、test 緩和、docs 上書きで解決した扱いにしてはいけません
- 同じ implementation pass で直せるのは、承認済み design、局所 precedent、既存責務境界から一意に導ける typo、format、import、狭い機械的追従だけです。判断が必要なら設計問題として扱います
- validation の test / check failure を見た場合は、implementation intent の変更、behavior / test の削除、revert、oracle weakening、pass 目的の単純化へ進む前に、`failing_contract`、`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を記録します。`cause_classification` と `intent_preservation` の slug set と route semantics は `documents/runtime-profiles-and-check-matrix.md`、`agents/canonical/CODEX_WORKFLOW.md`、`agents/canonical/CODEX_SUBAGENTS.md`、`documents/REVIEW_PROCESS.md` を参照します。`cause_classification=implementation_bug` で contract と oracle が安定している場合は、approved intent を保ち、追加 test planning で止めずに owning code / config / docs / workflow repair へ進めます
- design section、request clause ID、test plan item に trace できない変更は実装しません
- dependency manifest edge、reverse edge、または comment wrapping を設計と違う形で実装しません。必要なら Gate 5-6 へ戻します
- 非自明な変更では、final polish 前に checkpoint review を必ず 1 回挟みます
- 既存コード、既存 helper、既存 naming、既存 test style、既存 docs style を優先します
- 完全な新規実装より、既存実装の拡張、既存 pattern の模倣、既存 file layout の踏襲を優先します
- approved design または局所 precedent にない variable、function、class、file、CLI flag、config key、public API identifier を worker が作りません
- strictly local な一時変数名だけは、隣接コードの明白な pattern を mirror し、reusable API、file path、test name、user-facing surface に出ない場合に限って worker が決められます
- naming gap を見つけたら、実装で埋めずに Gate 5-6 へ戻します
- 実装 slice が終わったら、changed files、clause coverage、remaining planned work units、next required gate を記録して次段へ進みます
- 予定 work unit や active clause が残っている場合は、実装完了ではなく次の work unit へ進みます
- review artifact の指摘を受けて修正したら、その修正が tiny fix でも Gate 8 から required review family を最新 diff でやり直します。前の approve は失効します

必須レビュー:
- `change_reviewer`
  - 各 changed slice が `Abstract Design Frame`、approved design section、`Implementation Source Packet` entry、test plan item、request clause ID を引用しているか確認する
  - changed slice と関連 docs / workflow / prompt/config / validation / dependency-manifest update が approved `Design Side-Effect Map` に trace できるか確認する
  - changed slice が nearest file、helper、current finding、chat context だけで正当化され、抽象責務 model へ trace できない場合は revise blocker として扱う
  - changed human-authored text file が `@dependency-start` / `@dependency-end` 形式を持ち、旧 `Dependency Files:` block を残していないか確認する
  - 追加・変更された dependency edge に reverse edge、kind match、自己参照なし、cycle risk なしの evidence があるか確認する
  - design packet から外れた変更、または design gap を実装で埋めた変更を blocker として扱う
  - non-canonical design doc、implementation copy、snapshot、backup path が tracked tree に残っていないか確認する
  - chunk / slice の checkpoint approve を user request 全体の完了として扱っていないか確認する
  - remaining planned work units と next required gate が実装 handoff に残っているか確認する
  - implementation checkpoint review として、構造、境界、明白な回帰、設計逸脱を早期に確認する
  - `Large Delivery` では chunk ごとに最低 1 回
  - `Platform And Environment` では rollout 影響が見える時点で最低 1 回

exit 条件:
- 差分が requirements / plan / design に一致している
- 各 changed slice が `Abstract Design Frame`、approved design section、`Implementation Source Packet` entry、test plan item、request clause ID を引用している
- nearest file、helper、current finding、chat context だけで正当化された changed slice がない
- changed-file dependency manifest checks が pass している
- canonical path 以外の design / implementation truth surface が残っていない
- remaining planned work units がない、または次の work unit と gate が明記されている
- planned checks を実行できる状態になっている
- implementation checkpoint review が `resolved` になっている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate implementation"` が pass している

### Gate 9. 最終受け入れ review

目的:
- 差分が設計どおりで、回帰やリスクが許容範囲に収まっているか確認する

主担当:
- `final_reviewer`
- 必要に応じて `python-review`
- 必要に応じて `cpp-review`
- 必要に応じて `md-style-check`
- 必要に応じて `critical-review`

最低限の確認:
- code / docs diff review
- validation plan の実行
- security / safety / provenance の確認

必須レビュー:
- `final_reviewer`
  - 変更全体、docs 同期、受け入れ条件達成、不要な新規 pattern の混入有無を確認する
  - final diff が Abstract Design Frame、approved design section、Implementation Source Packet、request clause ID、test plan item に trace できるか確認する
  - final diff の side-effect coverage が approved Design Side-Effect Map と一致しているか確認する
  - final diff が Dependency Manifest Plan に trace でき、changed-file manifest scan / format / graph evidence が closeout に残っているか確認する
  - current tree head 以外の design / implementation truth surface が残っていないか確認する
- 必要に応じて `python-review`
  - Python API、型境界、test coverage の不足を確認する
- 必要に応じて `cpp-review`
  - C / C++ API、header 境界、build evidence、ownership と error path の不足を確認する
- 必要に応じて `md-style-check`
  - 文書体裁とリンク整合を確認する
- 必要に応じて `critical-review`
  - claim、evidence、overclaim を確認する

ルール:
- review で戻されたあとに入れる修正は、設計を変えない tiny fix でもこの gate 内だけで閉じません。Gate 8 に戻して差分を更新し、Gate 8 と Gate 9 の required review を最新 diff に対してやり直します
- review の `revise`、`required_change`、`rejected`、または requested-change は、
  user request や approved design intent を戻す権限ではありません。実装担当は
  同じ意図を保つ修正、同じ意図を保つ再設計、または design / scope conflict の
  escalation として扱います。実装 slice を削除、revert、discard する場合は、
  request clause の撤回 / 置換、owner 外、unsafe replacement、または escalation
  の authority と、保持した clause を review artifact に残します
- 新しい requirement が必要なら Gate 1 に戻します
- 計画変更が必要なら Gate 3 に戻します
- 設計変更が必要なら Gate 5 に戻します

exit 条件:
- `required_change` が解消している
- 実行した checks と未実行理由が説明できる
- dependency manifest checks と graph validation の実行結果または移行中 baseline 理由が説明できる
- final acceptance review が `resolved` になっている
- `final_review.md` に post-fix review rerun review が記録され、review-driven fix の後に risk class と changed surface に対する active required review set を rerun したことが追える
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate final"` が pass している

### Gate 10. Audit And Gate Closure

目的:
- 受け入れ条件を満たした変更だけを close する

主担当:
- `auditor`
- `verifier`

最低限の確認:
- acceptance criteria の達成
- repo 正本の同期
- closeout command の実行
- dependency manifest checks の実行
- commit / push の成否確認
- `verification.txt` の `status=pass`
- `closeout_gate.md` の `auditor_status=resolved` と `user_completion_report=unlocked`
- `closeout_gate.md` の `all_planned_chunks_complete=yes` と `overall_delivery_complete=yes`
- `closeout_gate.md` の `spec_product_coverage_complete=yes` と `review_findings_integrated=yes`
- `closeout_gate.md` の `post_fix_full_review_complete=yes`
- `closeout_gate.md` の `mechanical_completion_loop_complete=yes` と構造化 loop evidence
- `closeout_gate.md` の `diff_check_agent_complete=yes` と run-local diff-check artifact evidence
- `closeout_gate.md` の `canonical_tree_head_complete=yes`
- `user_request_contract.md` の `all_clauses_resolved=yes` と `forbidden_drift_detected=no`
- `schedule.md` の TODO 行が空ではない
- `work_log.md` に meaningful step が記録されている

必須レビュー:
- `auditor`
  - required reviews が揃っているか、artifact と closeout evidence が欠けていないか確認する

exit 条件:
- auditor review が `resolved` になっている
- verifier が gate を閉じている
- user-facing completion report の unlock 条件が `closeout_gate.md` に記録されている
- chunk、slice、checkpoint、subpass ではなく、user request 全体の完了であることが `Completion Boundary Evidence` に記録されている
- 仕様と product surface の gap が残っていないことが `Spec-To-Product Coverage Evidence` に記録されている
- required review の fix-now findings が反映済み、再レビュー済み、または escalated であることが `Review Finding Integration Evidence` に記録されている
- review reject / requested-change への応答が user-requested behavior の blanket
  revert ではなく、intent-preserving repair / redesign / escalation として
  証跡化されていることが `Review Finding Integration Evidence` に記録されている
- review-driven fix が入った場合、latest diff に対する full review rerun artifact が `Post-Fix Full Review Evidence` に記録されている
- planned work、review findings、validation、dependency review、static analysis、commit / push、shared canon sync、follow-up 判断を機械的に列挙した loop evidence が `Mechanical Completion Loop Evidence` に記録されている
- read-only diff-check agent の decision、latest diff ref、run-local artifact、findings disposition が `Diff-Check Agent Evidence` に記録され、artifact が `approve` を示している
- canonical design path と implementation path だけが tracked tree に残っていることが `Canonical Tree-Head Evidence` に記録されている
- user request clause の未解決がない

## 5. 差し戻しルール

- requirement の抜けやスコープ変更:
  - Gate 0 へ戻す
- 調査不足、existing code survey の不足:
  - Gate 1 へ戻す
- 実行計画の順序不備、agent 割当の不足:
  - Gate 2-3 へ戻す
- 設計不整合、file plan の見直し、rollback 方針の欠落:
  - Gate 4-5 へ戻す
- 実装ミスや test failure だが設計は維持できる:
  - `failing_contract`、`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を記録し、`cause_classification=implementation_bug` なら Gate 8 の owning implementation repair に戻す。slug set と route semantics は validation-failure-response owner surfaces を参照する
- 実験結果やユーザー要望で別仮説になった:
  - 既存 pass を閉じ、新しい change request として Gate 0 からやり直す

## 6. Pilot / Prototype の扱い

Royce の "do it twice" を踏まえ、この repo では pilot / prototype を次の条件で許可します。

- Gate 1 または Gate 2 のための学習目的である
- production path に直接 merge しない
- 何を確かめたかを記録する
- pilot の結果で要件か設計を更新したら、そのあとで本実装の waterfall pass を開始する

pilot は本実装の抜け道ではなく、requirements/design の凍結精度を上げる前段とみなします。

## 7. Family ごとの使い分け

### Scoped Change

- Gate 0 から Gate 10 をそのまま 1 pass で通します
- artifact は軽くて構いませんが、要件整理、計画、詳細設計、各 review の区別は崩しません
- `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer` を軽量版として必ず有効化します
- `document_flow_reviewer` は reader-facing docs、新用語、公開 API、workflow surface がある場合に有効化します

### Research-Driven Change

- literature survey、baseline run、比較設計は Gate 0-5 の入力です
- 1 回の code change は 1 回の waterfall pass で実装します
- `rerun_required` や新仮説が出たら、新しい pass としてやり直します

### Large Delivery

- `scheduler` が chunk を先に固定します
- 各 chunk は checkpoint review までを独立 subpass として閉じます
- chunk completion は user-facing completion ではありません
- chunk 間の横断変更は、umbrella pass の completion boundary に残し、必要なら次 chunk の Gate 1 に持ち越します
- 各 chunk の前に詳細設計文書を起こし、詳細設計レビューを通します
- 各 chunk で checkpoint review を複数回に増やして構いません

### Platform And Environment

- Gate 0-1 で code requirement、blocked command、必要 runtime capability を `environment_change_proposal.md` に固定します
- Gate 2-5 で source-of-truth surface、同期対象、rollout / rollback / environment impact を必ず固定します
- Gate 8-9 で `docker/`、CI、runtime pack、devcontainer、関連 README の同期を確認します
- Docker を変える pass では `bash tools/docker_dependency_validator.sh`、`python3 tools/ci/container_config.py`、`make docker-build-check`、必要なら `make docker-build-check-host-docker` を validation plan に含めます
- `infra_reviewer` は詳細設計レビューだけでなく最終受け入れ review にも参加して構いません

### Comprehensive Development

- code、docs、tests、workflow、tools、runtime をまたぐ umbrella pass に使います
- 背骨は 1 本の waterfall pass のままにし、surface ごとの差分を `schedule.md` の stage owner と write scope で切ります
- Gate 0-1 では `project_reviewer` を intake gate として使い、repo-wide completeness と collision risk を確認します
- Gate 3 では `Write Scope Ledger:`、`Writer Wave Order:`、`Integration Order:` を必ず固定します
- Gate 5-7 では `docs_workflow_steward` を canon docs 整理に使いますが、実装 worker と兼務させません
- Gate 8-9 では言語差分に応じて `python_reviewer` や `cpp_reviewer` と `project_reviewer` を通し、slice 単位ではなく全体整合を見ます
- parent が writer ごとの path / directory を `team_manifest.yaml` の write policy で管理します
- write scope が重なる場合は、writer ごとに current checkout 内の後続 wave へ serialize してから統合します

## 8. reuse-first の必須ルール

- まず既存 module、既存 helper、既存 abstraction を探します
- まず導入済みライブラリ、既存 module、既存 helper、既存 abstraction を探します
- 既存 API shape、命名、error handling、test style、docs style を優先します
- 新しい pattern を導入するときは、詳細設計文書に既存 pattern や導入済みライブラリでは足りない理由を書きます
- 新しい identifier や path は worker の自由裁量にせず、詳細設計の naming plan または明白な局所 precedent に結び付けます
- 既存コードを踏襲できるなら、完全新規実装を選びません

## 9. closeout の必須項目

- 実行した validation
- 未実行 validation と理由
- `python3 tools/agent_tools/check_dependency_headers.py --changed`
- `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing`
- `bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header`
- dependency edge を追加・変更した場合は `bash tools/agent_tools/check_dependency_graph.sh --print-edges` の結果、または移行中 baseline failure と今回差分で新規 graph error を増やしていない evidence
- 更新した repo 正本
- commit hash
- push の成否

## 関連正本

- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)
- [agents/canonical/CODEX_WORKFLOW.md](../canonical/CODEX_WORKFLOW.md)
- [agents/workflows/README.md](README.md)
- [agents/workflows/research-workflow.md](research-workflow.md)
- [agents/workflows/experiment-workflow.md](experiment-workflow.md)
- [agents/workflows/workflow-references.md](workflow-references.md)

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
