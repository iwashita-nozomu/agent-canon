<!--
@dependency-start
contract workflow
responsibility Documents 実装ウォーターフォールワークフロー for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines canonical Codex task gates
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest gates
downstream design ../templates/closeout_gate.md records closeout evidence required by this workflow
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py verifies design-doc evidence claims
upstream design ../skills/code-visualization.md sole public visualization owner and canonical projection gate
upstream implementation ../../tools/agent_tools/visualization_contract.py typed visualization coverage checker
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py validates workflow gate dependency edges
@dependency-end
-->

## Canonical Visualization Gate

When an implementation slice changes a visualization contract, owner route,
producer adapter, renderer, or formatter, Gate 5-6 design approval must exist
before the first contract edit. After the edit, route through the sole public
`code-visualization` owner and run its canonical ToolCall, projection coverage,
post-format readback, formatter, route, and producer-checker gates. Reference
the typed contract owned by `tools/agent_tools/visualization_contract.py`;
workflow prose must not copy its schema or omission/granularity policy.

Any failed gate returns the existing typed validation failure packet with
`failing_contract`, `observation_level`, `cause_classification`,
`intent_preservation`, and `evidence` before repair. A visualization slice
cannot enter implementation closeout while its canonical final coverage status
is not `pass`.

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

- selected stage に必要な subagent / specialist だけを explicit に立てる
- context sweep と library sweep を済ませる前に stage を始めない
- 要件が固まる前に code を書き始めない
- 計画が固まる前に詳細設計へ進まない
- 詳細設計が固まる前に実装を広げない
- 実装は承認済みの設計文書 packet を読んでから始める
- 設計文書と実装の正本を 1 本に固定し、tracked tree に parallel truth を残さない
- 実装、review、verification を段階ゲートで区切る
- review は候補であり、同じ replaceable responsibility の claims は一つの owning
  review gate で判定する。distinct unresolved claim/risk がその gate の判断範囲を
  超える場合だけ specialist review を追加する
- selected review の output が accepted finding を生む場合だけ、同じ owner の repair
  と selected gate の rerun を行う
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

1. subagent bootstrap (when delegation or lifecycle coordination is selected)
1. owner / responsibility / mechanism / validation sufficiency
1. requirements, research, plan, and design only when their unresolved decision can change the next owner or edit
1. implementation
1. conditional post-implementation test design only for an explicit unresolved oracle or failure risk
1. one selected owning review gate, with a specialist only for a distinct unresolved claim/risk
1. audit / gate close

`Scoped Change` の bounded 差分は、semantic sufficiency が owner、replaceable unit、
mechanism、validation route を閉じた場合、未選択の計画・設計・review stage を
materialize しません。reader-facing docs、新用語、公開 API、workflow surface の
unresolved claim が owning gate で判定できない場合だけ document-flow specialist を
選択します。
`test_designer` は default の実装前 gate ではありません。実装が owning mechanism を確立または修復した後、static analysis、既存 checker、targeted validation が所有しない具体的な oracle / specification / regression / failure-mode risk が残る場合だけ、条件付きの post-implementation route として起動します。ordinary code change、bug fix、parser change、validation failure だけでは起動しません。
`cause_classification=implementation_bug` の validation failure は、
`failing_contract`、`observation_level`、`cause_classification`、
`intent_preservation`、`evidence` を記録した後、追加 test planning で止めずに
owning implementation repair へ進めます。
contract-only wrapper pass では、static contract validation と canonical checker command を validation evidence にします。
この gate 順は implementation sequence です。独立 workstream が複数ある場合、parent は同じ sequence を workstream ごとの stage owner に割り当て、evidence と review gate に応じて vertical dynamic wave を追加します。

## 4A. 反復サイクル

この workflow は selected gate の decision が次の owner/edit/validation decision を
変える場合だけ repair cycle を持ちます。review not-needed は adjudicated decision
として closeout に記録し、固定 cycle や review artifact を作りません。
次段へ進む前の機械チェックは次を使います。

```bash
make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <requirements|plan|design|document_flow|test|implementation|final>"
```

`WATERFALL_GATE_READY=no` の場合は、`NEXT_ACTION` に出た owner stage へ戻し、空テンプレート、未承認 review、未記入 artifact を直してから再実行します。

### Cycle A. 条件付き計画・レビュー

- 対象:
  - Gate 3 実行計画立案
  - Gate 4 計画レビュー
- owner:
  - `scheduler`
- reviewer:
  - selected owning review gate only
- 反復規則:
  - selected review の decision が accepted repair を要求する場合だけ owning stage に戻します
  - `revise` は Gate 3 へ戻します
  - `escalate` は Gate 1 または Gate 2 へ戻して scope / research を修正します
- 完了条件:
  - stage 順序、handoff、rollback、validation sequence が hidden step なしで実行できる
  - selected review gate と parent-managed write-scope discipline が崩れていない

### Cycle B. 条件付き詳細設計・レビュー -> 文書通読レビュー

- 対象:
  - Gate 5 詳細設計
  - Gate 6 詳細設計レビュー (selected only for an unresolved owner/design claim)
  - Gate 7 文書通読レビュー (selected only for a reader-facing unresolved claim)
- owner:
  - `designer`
- reviewers:
  - `design_reviewer`
  - active gate の場合は `document_flow_reviewer`
- 反復規則:
  - Gate 5 で詳細設計を作成した後、Gate 6 は owner/design boundary、API shape、
    仕様解釈、または別の unresolved claim が owning review gate で判定できない
    場合だけ選択します。設計文書は review artifact の存在だけで別 wave を作りません
  - Gate 6 は実装 diff ではなく、Gate 5 で作られた同一の詳細設計文書
    そのものを review 対象にし、`design_review.md` に design artifact path
    と対象 revision / section を記録します
  - selected Gate 6 の decision が `approve` でない場合だけ Gate 5 に戻します。reviewer
    output は hypothesis であり、parent / integration owner が current snapshot、
    reachable path、contract、witness/static proof を確認して adjudicate します
  - 文書通読レビューが active gate の場合は、`document_flow_review.md` の decision が `approve` でない限り Gate 5 に戻します
  - accepted finding が behavior、owner/design boundary、correctness、validation、
    または publication state を変える場合だけ `revise` は Gate 5 へ戻します
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
  - selected owning review gate (`change_reviewer` when activated)
- 反復規則:
  - selected owning review gate がある場合、その decision が `approve` でない限り Gate 8 に戻します
  - selected gate の `revise` は Gate 8 へ戻します
  - selected gate の accepted `required_change`、または rejected slice への応答は、同じ
    request clause と approved design intent を保つ修正として行います
  - selected gate の `escalate` は Gate 5 へ戻して詳細設計を修正し、test-design route が
    active な場合だけ Gate 8.5 の evidence も更新します
- 完了条件:
- diff が approved design と canonical validation evidence に一致する
- 各実装 slice が design artifact、design section、request clause ID を引用し、
  test-design route が active な場合だけ test plan item も引用している
- tracked tree に non-canonical design doc、implementation copy、snapshot、backup path を増やしていない
- regression、style drift、stale path、missing test が blocker なしになる

### Gate 0. Subagent Bootstrap

目的:
- semantic handoff を先に固定し、coordination、resumption、または selected
  lifecycle route が必要な場合だけ run bundle と review artifact を materialize する
- reviewer は候補として扱い、one owning review gate を選択し、distinct unresolved
  claim/risk の場合だけ別 agent instance を割り当てる

最低限の記録:
- structured handoff の owner、replaceable unit、mechanism、validation route、unresolved branch
- durable coordination/resumption が選択された場合だけ、その route が要求する run-bundle files

条件付き追加 subagent:
- repo 内調査が要る場合は `explorer`
- 文書主体の整理が要る場合は `docs_workflow_steward`

必須ルール:
- 選択された route が必要とする場合だけ、`documents/`、`notes/`、`references/` と local library の sweep を行います
- durable artifact route が選択された場合だけ、`user_request_contract.md`、`schedule.md`、`work_log.md` をその route の正本として更新します
- repo-changing task の subagent は owner-critical operation、coordination/resumption、または selected unresolved risk がある場合だけ activate します
- active runtime が explicit user request なしの subagent spawn を禁止する場合は、actual spawn の代わりに `SUBAGENT_AUTHORIZATION=required`、role、input packet、expected output、review gate を structured handoff message/tool result に固定します。coordination/resumption が既に durable bundle を選択している場合だけ、その bundle を使います。許可が出るまでその specialist review を完了扱いにしません
- selected review claims が同じ owner、responsibility、context、write authority、validation route を共有する場合は active instance を再利用します。独立 review、disjoint authority、incompatible context、または owning gate で判定できない distinct unresolved claim/risk の場合だけ別 instance にします
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

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
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

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- ここでは plan review は行いません。次 gate で独立 reviewer に渡します。

ルール:
  - 実行計画を選択した場合は、詳細設計の前にその owner、validation route、次 gate を確定させます
- どの subagent / role がどの stage を担当するか明記します
- 包括的開発では、`Write Scope Ledger:` と `Integration Order:` を書きます
- 複数 writer が必要な場合は、writer ごとの disjoint path と current checkout 内の wave 順序を明記します。separate worktree は使いません

exit 条件:
- `schedule.md` に stage 順序、担当 agent、exit criteria、validation が書かれている
- `schedule.md` に clause coverage が書かれている
- `schedule.md` の `Planned Work Units` が TODO として具体化されている
  - 実装へ進む前に selected review gate の owner と evidence が割り当てられている、または not-needed が adjudicated されている

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

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- `schedule_reviewer`
  - stage 順序、依存関係、selected review gate、rollback point を確認する
- 必要に応じて `infra_reviewer`
  - runtime、CI、Docker、dependency 影響が計画に反映されているか確認する

ルール:
- one owning review gate で判定できる計画・設計 claims は同じ compatible instance を再利用します。別 instance は独立 review、disjoint authority、incompatible context、または distinct unresolved claim/risk の場合だけ選択します
- candidate stage は飛ばしや merge ができます。owner-critical decision、distinct
  unresolved claim/risk、または selected validation route が要求した stage だけを
  schedule し、selected stage の順序と gate evidence は保持します
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
- `Implementation Source Packet` には、worker が編集前に読む `user_request_contract.md`、`schedule.md`、`design_brief.md`、selected の場合の `design_review.md`、active な場合の `document_flow_review.md`、repo docs、dependency surface、code path、test path、外部 reference を列挙します。`test_plan.md` は Gate 8.5 が active になった後の review packet にだけ加えます
- `Design Side-Effect Map` には、主要設計判断ごとに影響する implementation、document、workflow、prompt/config、validation、dependency manifest、user-facing surface を列挙し、各 item を `Abstract Design Frame`、request clause ID、reuse precedent、owner stage、review gate、canonical validation evidence に接続します。test-design route が active な場合だけ test-plan item も接続します
- `Dependency Manifest Plan` には、編集対象 file ごとに追加・維持する `upstream` / `downstream` edge、kind、相対 path、reason、編集前に読む upstream context、編集後に確認する downstream context を列挙します
- 新規・変更する human-authored text file では旧 `Dependency Files:` block を使わず、`documents/dependency-manifest-design.md` の `@dependency-start` / `@dependency-end` 形式に統一します
- 新しい dependency edge を足す場合は reverse edge も同じ pass の file plan に入れます。移行中で reverse edge 追加を同じ pass に含められない場合は、design review に blocker か明示 escalation として出します
- `Canonical Tree-Head Plan` では、task 完了後に tracked tree に残してよい canonical design path と canonical implementation path を固定し、parallel design doc、implementation copy、dated snapshot、backup file、duplicate directory を作らないことを明示します
- `bootstrap_agent_run.py` と `task_start.py` は `DESIGN_DOCUMENT_PACKET` と `IMPLEMENTATION_DOCUMENT_PACKET` を出力します。parent は designer / implementer subagent 起動時にその path 群をそのまま渡します
- `Design-To-Implementation Trace` には、各予定差分ごとに design section、request clause ID、source / reuse 文書または code path、validation evidence を対応付けます。test-design route が active な場合だけ test plan item も対応付けます
- 新規 helper、new module、new dependency、new public API を足す差分では、既存実装や導入済みライブラリでは足りない理由を `Design-To-Implementation Trace` に対応付けます
- 既存 module boundary、命名、API shape、test style、docs style から逸脱する場合は、理由を明示します
- 新規または rename する variable、function、class、file、CLI flag、config key、public API identifier は、既存 precedent、採用名、却下した代替案、review 観点を明記します
- 既存 precedent がある場合はそれを採用し、ない場合は理由を文書化して Gate 6 で確認します
- worker が naming、API shape、path layout、boundary choice を発明しなくてよい状態まで詳細設計を詰めます
- worker が会話文脈や記憶を実装入力にしなくてよい状態まで、必要な判断を設計文書内に再掲します
- worker が chat 要約ではなく packet path を実際に読めるよう、document packet は absolute path で明示します
- Gate 5 が詳細設計を作成したら、designer は unresolved claim がある場合だけ
  `design_review_required=yes` として Gate 6 に渡します。その他は selected owning
  gate へ直接 handoff します
- refactor pass では semantic delta を feature 追加として混ぜません
- refactor pass では path mapping と remove list を実装前に固定します
- structure refactor では recursive directory README graph と dependency / responsibility-scope evidence から path mapping を作り、README 更新だけで構造矛盾を隠しません
- 包括 refactor では、必要に応じて `tools/agent_tools/analyze_refactor_surface.py` または task 固有解析 tool の score を design gate に入れます。score pass は behavior evidence の代替ではなく、責務境界の補助 evidence として扱います
- Gate 6 または Gate 7 の accepted finding が design / reader-facing decision を
  変える場合だけ Gate 5 へ戻ります。rejected finding は `reason_code` と
  `evidence_ref` を残し、wave / rollback を起こしません

exit 条件:
- 実装者が文書だけ読んで着手できる
- designer が upstream 文書だけ読んで詳細設計に着手できる
- worker が編集前に確認する抽象責務と、編集前に読む文書 / code path が `Abstract Design Frame` と `Implementation Source Packet` だけで分かる
- 実装対象 file、helper、current finding に絞る前の抽象責務と概念 model が `Abstract Design Frame` だけで分かる
- 設計判断の downstream side effect が `Design Side-Effect Map` から owner stage、review gate、validation route へ辿れる
- worker が編集前に読む upstream dependency context と、編集後に確認する downstream dependency context を `Dependency Manifest Plan` だけで分かる
- 各予定差分が `Design-To-Implementation Trace` で clause、source、validation へ結び付いている。test-design route が active な場合だけ test evidence にも結び付いている
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

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- `design_reviewer`
  - `design_review.md` の `Design Artifact Under Review` に、対象の
    `design_brief.md` path、対象 revision / section、review した source packet
    を記録する
  - implementation diff、worker summary、または parent の会話要約ではなく、
    Gate 5 の詳細設計文書そのものを判定対象にする
  - 文書 completeness、実装可能性、既存コード再利用、既存の書き方踏襲、不要な新規性を確認する
  - `Abstract Design Frame` が実装対象 file、既存 helper、current finding より先に抽象責務、概念 model、非対象、将来 layer、評価軸、既存正本との関係を固定し、そこから実装 slice を導いているか確認する
  - `Installed Libraries And Existing Implementation Survey` が dependency surface、既存実装候補、reuse 判断、既存では足りない理由を列挙しているか確認する
  - `Implementation Source Packet` が編集前に読む artifact、repo docs、dependency surface、code path を列挙し、test plan を実装前提にしていないか確認する
  - `Design Side-Effect Map` が主要設計判断から downstream surface、owner stage、review gate、canonical validation evidence へ trace できるか確認する
  - `Dependency Manifest Plan` が各 touched file の `@dependency-start` block、upstream / downstream edge、reverse edge、読む順序、検証 command に落ちているか確認する
  - 旧 `Dependency Files:` block を新規・変更 file に残す設計を blocker として扱う
  - `Canonical Tree-Head Plan` が current tree head だけを durable state にし、non-canonical design / implementation path を排除しているか確認する
  - 各予定差分が design section、request clause ID、reuse/source 文書または code path、validation evidence へ trace できるか確認し、test-design route が active な場合だけ test plan item も確認する
  - worker が会話文脈や記憶を使わないと実装できない箇所を blocker として確認する
  - identifier naming plan が既存 precedent または明示 rationale に結び付いているか確認する
  - worker が reusable / user-facing な名前を発明する余地が残っていないか確認する
- 必要に応じて `infra_reviewer`
  - infra / runtime 影響が設計文書に落ちているか確認する
- `project_reviewer`
  - refactor pass では stale path、cross-module drift、delete 漏れを確認する

ルール:
- `詳細設計レビュー` は candidate gate です。one owning review gate が判断できない
  distinct unresolved claim のときだけ有効化します
- selected `design_review.md` の decision が `approve` になるまで、その design claim
  を前提にした実装へ進みません。candidate artifact の不在だけでは停止しません
- 承認は latest design artifact にだけ有効です。Gate 5 で設計を修正したら、
  旧 `approve` を流用せず Gate 6 を再実行します
- parent が accepted と adjudicate した design concern を解消しないまま実装へ進みません
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
- selected design review がある場合は decision が `approve` になっている
- selected design review がある場合は `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate design"` が pass している。未選択の場合は semantic decision sufficiency と owner validation evidence を記録する

### Gate 7. 文書通読レビュー

目的:
- 文書を上から順に読んだときに、最初の reader が意味を追えるか確認する

主担当:
- `document_flow_reviewer`

条件付き追加 subagent:
- `reviewer`
- 文書差分が大きいなら追加で `project_reviewer`

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- `document_flow_reviewer`
  - section 順序、用語の先出し、前提の提示順、結論までの reader path を確認する
  - 「途中で前提が出る」「定義前の語が出る」「どこを読めば判断できるか分からない」を blocker として扱う

ルール:
- selected `document_flow_reviewer` は、owning gate と同じ context / validation route で判定できる場合はその gate の instance を再利用し、distinct unresolved reader-path claim の場合だけ別 instance にします
- 文書主体の成果物で document-flow review が selected の場合、top-down readthrough で major rewrite が必要なまま実装へ進みません

exit 条件:
- selected の場合は `document_flow_review.md` が `resolved` になっている。未選択の場合は not-needed の adjudication がある
- 上から順に読んだときの意味の飛び、定義不足、section order の問題が解消している

### Gate 8. 実装

目的:
- 凍結済みの設計を実装へ落とす

主担当:
- write-capable Codex implementer selected from `IMPLEMENTATION_CODEX_AGENTS`
  (`worker` by default; `spark_worker` only through
  `--select-agent-type implementer=spark_worker:<evidence>` recorded in stdout /
  manifest for a bounded low-risk slice)
- parent is the gate owner / integrator only

条件付き追加 subagent:
- additional selected write-capable implementer instances only when
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
- Gate 8 cannot start from a detailed design when a selected design review is
  unresolved. In that case `pre_handoff_gate_status` records the current design
  artifact, `design_review.md decision=approve`, and
  `waterfall-gate-check --gate design` pass evidence. A candidate review does not
  block the handoff.
- Parent-Direct Context Note is a routing / handoff artifact, not edit
  authorization. Once edit scope is known, launch or schedule the selected
  write-capable implementer. If the selected candidate is blocked, record
  local/tool evidence with `selected_agent_type`,
  `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and
  `status=blocked`; changing candidates requires a revised parent packet and
  wave.
  Record `WRITE_SUBAGENT_AUTHORIZATION=required` or
  `write_capable_handoff_blocker=<gate>` before any parent-direct exception.
- chunk、slice、checkpoint、subpass は内部進捗であり、user request 全体の完了ではありません
- 実装前に `Abstract Design Frame`、`Implementation Source Packet`、`Design Side-Effect Map` の全項目、`design_review.md`、active な場合の `document_flow_review.md` を読み、抽象責務と概念 model から実装 slice が導かれていることを実装 summary に残します。`test_plan.md` は test-design route が明示的に activate された場合だけ参照し、実装の前提にしません
- 実装前に `Dependency Manifest Plan` の upstream edge target を読み、編集後に downstream edge target を確認します
- 実装前に `Installed Libraries And Existing Implementation Survey` を読み、既存ライブラリ拡張か既存実装拡張か新規追加かの判断を実装 summary に残します
- 会話、記憶、直感を、承認済み設計文書より優先しません
- design artifact と現在の repo docs / code が矛盾する場合は、実装で解釈せず Gate 5-6 へ戻します
- 実装は 1 つの change request に閉じます
- tests は concrete behavior regression oracle が承認された場合だけ変更し、docs と同じ pass での更新を既定にしません
- 途中で scope を広げません
- 設計を変えたくなったら Gate 5-6 を開き直します
- 実装中に設計上の問題を見つけた場合は、勝手に実装で吸収せず `design_issue_blocker` と evidence を残して Gate 5-6 へ戻します。対象は API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾です。local fallback、wrapper、helper、分岐、互換 route、test 緩和、docs 上書きで解決した扱いにしてはいけません
- 同じ implementation pass で直せるのは、承認済み design、局所 precedent、既存責務境界から一意に導ける typo、format、import、狭い機械的追従だけです。判断が必要なら設計問題として扱います
- validation の test / check failure を見た場合は、implementation intent の変更、behavior / test の削除、revert、oracle weakening、pass 目的の単純化へ進む前に、`failing_contract`、`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を記録します。`cause_classification` と `intent_preservation` の slug set と route semantics は `documents/runtime-profiles-and-check-matrix.json` を canonical taxonomy owner として cite し、`documents/runtime-profiles-and-check-matrix.md` を generated reader projection として扱います。workflow、subagent、review surface は required evidence と same-intent repair / escalation result だけを記録します。`cause_classification=implementation_bug` で contract と oracle が安定している場合は、approved intent を保ち、追加 test planning で止めずに owning code / config / docs / workflow repair へ進めます
- design section、request clause ID に trace できない変更は実装しません。test-design route が activate された場合だけ、その evidence を test-plan item に trace します
- dependency manifest edge、reverse edge、または comment wrapping を設計と違う形で実装しません。必要なら Gate 5-6 へ戻します
- 非自明な変更では、selected owning review gate を final polish 前に adjudicate します。別 checkpoint review は distinct unresolved claim/risk が owning gate で判定できない場合だけ追加します
- 既存コード、既存 helper、既存 naming、既存 test style、既存 docs style を優先します
- 完全な新規実装より、既存実装の拡張、既存 pattern の模倣、既存 file layout の踏襲を優先します
- approved design または局所 precedent にない variable、function、class、file、CLI flag、config key、public API identifier を worker が作りません
- strictly local な一時変数名だけは、隣接コードの明白な pattern を mirror し、reusable API、file path、test name、user-facing surface に出ない場合に限って worker が決められます
- naming gap を見つけたら、実装で埋めずに Gate 5-6 へ戻します
- 実装 slice が終わったら、changed files、clause coverage、remaining planned work units、next required gate を記録して次段へ進みます
- 予定 work unit や active clause が残っている場合は、実装完了ではなく次の work unit へ進みます
- reviewer output は hypothesis です。accepted finding が behavior、owner/design
  boundary、correctness、validation、または publication state を変える場合だけ Gate
  8 の same-owner repair と selected owning gate の rerun を行います。duplicate、
  stylistic、already-covered、evidence-free、unreachable、stale、private/incidental、
  out-of-scope、または unproven design-conflict finding は `reason_code` と
  `evidence_ref` を残して wave / rollback を起こしません

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- `change_reviewer`
  - 各 changed slice が `Abstract Design Frame`、approved design section、`Implementation Source Packet` entry、request clause ID を引用し、test-design route が active な場合だけ test plan item も引用しているか確認する
  - changed slice と関連 docs / workflow / prompt/config / validation / dependency-manifest update が approved `Design Side-Effect Map` に trace できるか確認する
  - changed slice が nearest file、helper、current finding、chat context だけで正当化され、抽象責務 model へ trace できない場合は revise blocker として扱う
  - changed human-authored text file が `@dependency-start` / `@dependency-end` 形式を持ち、旧 `Dependency Files:` block を残していないか確認する
  - 追加・変更された dependency edge に reverse edge、kind match、自己参照なし、cycle risk なしの evidence があるか確認する
  - design packet から外れた変更、または design gap を実装で埋めた変更を blocker として扱う
  - non-canonical design doc、implementation copy、snapshot、backup path が tracked tree に残っていないか確認する
  - chunk / slice の checkpoint approve を user request 全体の完了として扱っていないか確認する
  - remaining planned work units と next required gate が実装 handoff に残っているか確認する
  - selected owning review gate として、構造、境界、明白な回帰、設計逸脱を確認する
  - `Large Delivery` または `Platform And Environment` の追加 review は、distinct unresolved claim/risk が必要な場合だけ選択する

exit 条件:
- 差分が requirements / plan / design に一致している
- 各 changed slice が `Abstract Design Frame`、approved design section、`Implementation Source Packet` entry、request clause ID を引用し、test-design route が active な場合だけ test plan item も引用している
- nearest file、helper、current finding、chat context だけで正当化された changed slice がない
- changed-file dependency manifest checks が pass している
- canonical path 以外の design / implementation truth surface が残っていない
- remaining planned work units がない、または次の work unit と gate が明記されている
- planned checks を実行できる状態になっている
- selected owning review gate が `resolved`、または review not-needed が adjudicated されている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate implementation"` が pass している

### Gate 8.5. 実装後の条件付きテストケース設計

目的:
- 実装が owning mechanism を確立または修復した後、static analysis、既存 checker、targeted validation が所有しない具体的な oracle / specification / regression / failure-mode risk が残る場合だけ、test-design evidence を追加する

主担当:
- `test_designer`

起動条件:
- implementer が mechanism の確立または修復を記録している
- parent が具体的な unresolved risk と、既存 validation がその risk を所有しない根拠を記録している

最低限の記録:
- `Activation Decision:`
- `Static Path Survey:`
- `Nasty Cases:`
- `Regression Cases To Keep:`
- `Implementation Notes:`

ルール:
- 条件を満たさない場合は `activation=not_needed` または `activation=deferred` だけを返し、`test_plan.md` を必須にせず、test-design tool を実行しません
- `test_designer` は read-only とし、repo file は編集しません
- checker-owned property は static analysis、checker、formatter、dependency review、type checking、lint、docs check、または targeted validation へ戻します
- tests は concrete behavior regression oracle がある場合だけ作成または編集し、既存 tests は evidence として扱います
- validation test / check が失敗した場合は、`failing_contract`、`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を先に記録し、意図を弱めて pass を作りません
- `cause_classification=implementation_bug` で contract と oracle が安定している場合は、approved intent を保った owning implementation repair へ戻します

exit 条件:
- activation decision が記録されている
- `activation=required` の場合だけ、具体的な behavior regression oracle とその test-plan evidence が記録されている
- `activation=not_needed` または `activation=deferred` の場合、不要な test-plan artifact や tool run を要求していない

### Gate 9. 条件付き受け入れ review

目的:
- 差分が設計どおりで、回帰やリスクが許容範囲に収まっているか確認する

主担当:
- selected owning review gate
- `final_reviewer` は final escalation または owning gate が判定できない distinct unresolved claim の場合だけ
- 必要に応じて `python-review`
- 必要に応じて `cpp-review`
- 必要に応じて `md-style-check`
- 必要に応じて `critical-review`

最低限の確認:
- code / docs diff review
- validation plan の実行
- security / safety / provenance の確認

選択レビュー:
- `final_reviewer` は final escalation または owning gate が判定できない distinct
  unresolved claim の場合だけ起動します
  - 変更全体、docs 同期、受け入れ条件達成、不要な新規 pattern の混入有無を確認する
  - final diff が Abstract Design Frame、approved design section、Implementation Source Packet、request clause ID、canonical validation evidence に trace でき、test-design route が active な場合だけ test plan item にも trace できるか確認する
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
- reviewer output は hypothesis です。current snapshot、reachable path、contract、
  witness/static proof があり、behavior、owner/design boundary、correctness、validation、
  または publication state を変える accepted finding だけ Gate 8 の same-owner repair
  に戻します。rejected finding は `reason_code` と `evidence_ref` を記録し、rollback / wave
  を起こしません
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
- accepted `required_change` が解消している。rejected hypotheses は `reason_code` と `evidence_ref` を持ち、修復 wave を開かない
- 実行した checks と未実行理由が説明できる
- dependency manifest checks と graph validation の実行結果または移行中 baseline 理由が説明できる
- selected owning review gate が `resolved`、または review not-needed が adjudicated されている
- selected review gate の artifact に accepted repair 後の rerun evidence が記録され、
  review-driven fix の後に changed surface に対する active gate を rerun したことが追える
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
- `closeout_gate.md` の `completion_coverage_consumer=yes`、`coverage_check.ok=true`、および `completion_boundary.topology_errors=[]`
- selected review gate の post-fix evidence (full review は touched contract が要求する final candidate の場合だけ)
- `closeout_gate.md` の `mechanical_completion_loop_complete=yes` と構造化 loop evidence
- selected diff-check review がある場合だけ `closeout_gate.md` の `diff_check_agent_complete=yes` と run-local artifact evidence
- `closeout_gate.md` の `canonical_tree_head_complete=yes`
- `user_request_contract.md` の `all_clauses_resolved=yes` と `forbidden_drift_detected=no`
- `schedule.md` の TODO 行が空ではない
- `work_log.md` に meaningful step が記録されている

選択レビュー (owner-critical decision または distinct unresolved claim/risk):
- `auditor`
  - selected reviews が揃っているか、activated artifact と closeout evidence が欠けていないか確認する

exit 条件:
- auditor review が `resolved` になっている
- verifier が gate を閉じている
- user-facing completion report の unlock 条件が `closeout_gate.md` に記録されている
- chunk、slice、checkpoint、subpass ではなく、user request 全体の完了であることが `Completion Boundary Evidence` に記録されている
- 仕様と product surface の gap が残っていないことが `Spec-To-Product Coverage Evidence` に記録されている
- accepted review findings のみが反映済み、再レビュー済み、または escalated であることを `Review Finding Integration Evidence` に記録し、rejected findings は `reason_code` と `evidence_ref` を残す
- review reject / requested-change への応答が user-requested behavior の blanket
  revert ではなく、intent-preserving repair / redesign / escalation として
  証跡化されていることが `Review Finding Integration Evidence` に記録されている
- review-driven fix が入った場合、changed behavior / owner / correctness / validation / publication を変えた accepted finding に限り selected gate の latest diff rerun evidence を記録する。full review rerun は final candidate が要求した場合だけ行う
- planned work、review findings、validation、dependency review、static analysis、commit / push、shared canon sync、follow-up 判断を機械的に列挙した loop evidence が `Mechanical Completion Loop Evidence` に記録されている
- selected owning review gate の decision、latest diff ref、findings disposition が記録される。read-only diff-check artifact はその gate が選択した場合だけ要求する
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
  - `failing_contract`、`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を記録し、`cause_classification=implementation_bug` なら Gate 8 の owning implementation repair に戻す。slug set と route semantics は `documents/runtime-profiles-and-check-matrix.json` を canonical taxonomy owner として cite し、`documents/runtime-profiles-and-check-matrix.md` を generated reader projection として扱う
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
- `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer` は候補です。owner-critical
  decision または distinct unresolved claim/risk が選択した role だけ有効化します
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
- 各 chunk の前に必要な詳細設計を起こし、owning gate が判定できない distinct unresolved design claim がある場合だけ詳細設計レビューを選択します
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
- Gate 8-9 の post-implementation change review は一つの owning review gate を選択します。
  `diff_triage_reviewer`、`python_reviewer` / `cpp_reviewer`、`project_reviewer` は changed
  path または distinct unresolved claim/risk が owning gate で判定できない場合だけ追加します
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
