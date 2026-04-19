# 実装ウォーターフォールワークフロー

この文書は、repo に変更を入れる実装プロセスを、段階ゲート付きのウォーターフォールとして進めるための正本です。
対象は `python/`、`documents/`、`agents/`、`docker/`、`scripts/` など、repo に持ち帰る変更全般です。

この repo では workflow family の選択は `agents/TASK_WORKFLOWS.md` を使いますが、実装そのものの進め方はこの文書を共通ルールにします。
README、workflow、guide、migration 文書のような長文では、加えて `agents/workflows/long-form-writing-workflow.md` を overlay として使います。
論文、thesis chapter、scholarly note のような学術文章では、`agents/workflows/academic-writing-workflow.md` を優先 overlay として使います。

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

この workflow では、最小でも次の stage を順に通します。

1. subagent bootstrap
1. 要件整理
1. 調査
1. 実行計画立案
1. 計画レビュー
1. 詳細設計
1. 詳細設計レビュー
1. 文書通読レビュー
1. テストケース設計
1. 実装
1. 実装 checkpoint review
1. 最終受け入れ review
1. audit / gate close

`Scoped Change` のような小さい差分でも、実行計画、計画レビュー、詳細設計、詳細設計レビュー、文書通読レビューを省略しません。
また、`計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別エージェントで行います。とくに `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします。
code を変える pass では、実装前に `test_designer` を独立に立て、static path と nasty case を test plan として固定します。

## 4A. 反復サイクル

この workflow は gate を 1 回通過して終わりではありません。次の 3 つの cycle を持ち、各 cycle は review decision が `approve` になるまで反復します。
次段へ進む前の機械チェックは次を使います。

```bash
make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <requirements|plan|design|test|implementation|final>"
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
  - review 分離と single-writer discipline が崩れていない

### Cycle B. 詳細設計 -> 詳細設計レビュー -> 文書通読レビュー

- 対象:
  - Gate 5 詳細設計
  - Gate 6 詳細設計レビュー
  - Gate 7 文書通読レビュー
- owner:
  - `designer`
- reviewers:
  - `design_reviewer`
  - `document_flow_reviewer`
- 反復規則:
  - `design_review.md` または `document_flow_review.md` の decision が `approve` でない限り Gate 5 に戻します
  - `revise` は Gate 5 へ戻します
  - `escalate` は Gate 3 へ戻して設計方針を組み替えます
- 完了条件:
- 実装者が文書だけ読んで着手できる
- `Implementation Source Packet` と `Design-To-Implementation Trace` が揃っている
- `Canonical Tree-Head Plan` が、正本として残す設計文書 path / 実装 path と削除対象の non-canonical path を明示している
- reuse-first、style-following、reader path が blocker なしで揃っている

### Cycle C. 実装 -> 実装 checkpoint review

- 対象:
  - Gate 9 実装
  - Gate 10 実装 checkpoint review
- owner:
  - `implementer`
- reviewer:
  - `change_reviewer`
- 反復規則:
  - `change_review.md` の decision が `approve` でない限り Gate 9 に戻します
  - `revise` は Gate 9 へ戻します
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
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別 agent instance で行います
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします
- 包括的開発では、同一 worktree の writer を 1 人に固定します
- 包括的開発では、同一 worktree の parallel write を許可しません

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
- 包括的開発では、`Single Writer Worktree:` と `Integration Order:` を書きます
- 複数 writer が必要な場合は、worktree ごとの writer を明記します

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
- `Implementation Source Packet:`
- `Canonical Tree-Head Plan:`
- `Patterns And Writing Style To Mirror:`
- `File-By-File Design:`
- `Design-To-Implementation Trace:`
- `Interfaces And Boundaries:`
- `Identifier And Naming Plan:`
- `Validation And Rollback Plan:`
- refactor pass では追加で `Behavior Contract:`, `Allowed Structural Delta:`, `Forbidden Semantic Delta:`, `Files To Remove Or Move:`, `Path Mapping:` を残します

ルール:
- 詳細設計の目標は、実装前に読むべき文書を完成させることです
- `Upstream Requirement Packet` には、designer が詳細設計前に読んだ `user_request_contract.md`、`schedule.md`、`intent_brief.md`、waterfall 正本、governing doc の path を列挙します
- `Implementation Source Packet` には、worker が編集前に読む `user_request_contract.md`、`schedule.md`、`design_brief.md`、`design_review.md`、`document_flow_review.md`、`test_plan.md`、repo docs、code path、test path、外部 reference を列挙します
- `Canonical Tree-Head Plan` では、task 完了後に tracked tree に残してよい canonical design path と canonical implementation path を固定し、parallel design doc、implementation copy、dated snapshot、backup file、mirror directory を作らないことを明示します
- `bootstrap_agent_run.py` と `task_start.py` は `DESIGN_DOCUMENT_PACKET` と `IMPLEMENTATION_DOCUMENT_PACKET` を出力します。parent は designer / implementer subagent 起動時にその path 群をそのまま渡します
- `Design-To-Implementation Trace` には、各予定差分ごとに design section、request clause ID、source / reuse 文書または code path、test plan item、validation evidence を対応付けます
- 既存 module boundary、命名、API shape、test style、docs style から逸脱する場合は、理由を明示します
- 新規または rename する variable、function、class、file、CLI flag、config key、public API identifier は、既存 precedent、採用名、却下した代替案、review 観点を明記します
- 既存 precedent がある場合はそれを採用し、ない場合は理由を文書化して Gate 6 で確認します
- worker が naming、API shape、path layout、boundary choice を発明しなくてよい状態まで詳細設計を詰めます
- worker が会話文脈や記憶を実装入力にしなくてよい状態まで、必要な判断を設計文書内に再掲します
- worker が chat 要約ではなく packet path を実際に読めるよう、document packet は absolute path で明示します
- refactor pass では semantic delta を feature 追加として混ぜません
- refactor pass では path mapping と remove list を実装前に固定します
- Gate 6 または Gate 7 が `revise` / `escalate` を返したら Gate 5 へ戻ります

exit 条件:
- 実装者が文書だけ読んで着手できる
- designer が upstream 文書だけ読んで詳細設計に着手できる
- worker が編集前に読む文書と code path が `Implementation Source Packet` だけで分かる
- 各予定差分が `Design-To-Implementation Trace` で clause、source、test、validation へ結び付いている
- 新規 abstraction より reuse-first の方針が説明できる
- 新規または rename する identifier と path の naming plan が文書だけで追える
- refactor pass では move / rename / split と挙動保存境界が文書だけで追える

### Gate 6. 詳細設計レビュー

目的:
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
  - 文書 completeness、実装可能性、既存コード再利用、既存の書き方踏襲、不要な新規性を確認する
  - `Implementation Source Packet` が編集前に読む artifact、repo docs、code path、test plan を列挙しているか確認する
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
- design reviewer が未解消の懸念を残したまま実装へ進みません
- naming plan、API shape、path layout、boundary choice の不足は `revise` blocker とします
- `Implementation Source Packet` または `Design-To-Implementation Trace` の不足は `revise` blocker とします
- refactor pass では `project_reviewer` の stale path 指摘を未解消のまま実装へ進みません
- `design_review.md` の decision は `approve`、`revise`、`escalate` のいずれかに固定します

exit 条件:
- `design_review.md` が `resolved` になっている
- reuse-first と style-following の懸念が解消している
- implementation source packet と design-to-implementation trace の懸念が解消している
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
- 実装前に static path を洗い、境界ケース、failure path、regression-prone case を test plan に落とす

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
- 実装者は test plan を読んで tests を同じ pass で落とし込みます

exit 条件:
- `test_plan.md` が作られている
- boundary case、malformed input、error path、state transition、regression case が明示されている
- `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate test"` が pass している

### Gate 8. 実装

目的:
- 凍結済みの設計を実装へ落とす

主担当:
- `implementer`

条件付き追加 subagent:
- bounded な切り出しだけを `worker` に渡す

ルール:
- chunk、slice、checkpoint、subpass は内部進捗であり、user request 全体の完了ではありません
- 実装前に `Implementation Source Packet` の全項目、`design_review.md`、`document_flow_review.md`、`test_plan.md` を読み、実装 summary に読んだ design artifact と section を残します
- 会話、記憶、直感を、承認済み設計文書より優先しません
- design artifact と現在の repo docs / code が矛盾する場合は、実装で解釈せず Gate 5-6 へ戻します
- 実装は 1 つの change request に閉じます
- docs と tests は同じ pass で更新します
- `test_plan.md` の nasty case を最低限どこへ落とし込んだか説明できるようにします
- 途中で scope を広げません
- 設計を変えたくなったら Gate 5-6 を開き直します
- design section、request clause ID、test plan item に trace できない変更は実装しません
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
  - 各 changed slice が design artifact、design section、source packet entry、test plan item、request clause ID を引用しているか確認する
  - design packet から外れた変更、または design gap を実装で埋めた変更を blocker として扱う
  - non-canonical design doc、implementation copy、snapshot、backup path が tracked tree に残っていないか確認する
  - chunk / slice の checkpoint approve を user request 全体の完了として扱っていないか確認する
  - remaining planned work units と next required gate が実装 handoff に残っているか確認する
  - implementation checkpoint review として、構造、境界、明白な回帰、設計逸脱を早期に確認する
  - `Large Delivery` では chunk ごとに最低 1 回
  - `Platform And Environment` では rollout 影響が見える時点で最低 1 回

exit 条件:
- 差分が requirements / plan / design に一致している
- 各 changed slice が design artifact、design section、test plan item、request clause ID を引用している
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
  - final diff が approved design section、Implementation Source Packet、request clause ID、test plan item に trace できるか確認する
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
- 新しい requirement が必要なら Gate 1 に戻します
- 計画変更が必要なら Gate 3 に戻します
- 設計変更が必要なら Gate 5 に戻します

exit 条件:
- `required_change` が解消している
- 実行した checks と未実行理由が説明できる
- final acceptance review が `resolved` になっている
- `final_review.md` に post-fix full review rerun review が記録され、review-driven fix の後に full required review set を rerun したことが追える
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
- commit / push の成否確認
- `verification.txt` の `status=pass`
- `closeout_gate.md` の `auditor_status=resolved` と `user_completion_report=unlocked`
- `closeout_gate.md` の `all_planned_chunks_complete=yes` と `overall_delivery_complete=yes`
- `closeout_gate.md` の `spec_product_coverage_complete=yes` と `review_findings_integrated=yes`
- `closeout_gate.md` の `post_fix_full_review_complete=yes`
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
- review-driven fix が入った場合、latest diff に対する full review rerun artifact が `Post-Fix Full Review Evidence` に記録されている
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
  - Gate 7 に戻して修正する
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
- `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer` を軽量版として必ず有効化します

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
- Docker を変える pass では `bash tools/docker_dependency_validator.sh`、`make docker-build-check`、必要なら `make docker-build-check-host-docker` を validation plan に含めます
- `infra_reviewer` は詳細設計レビューだけでなく最終受け入れ review にも参加して構いません

### Comprehensive Development

- code、docs、tests、workflow、tools、runtime をまたぐ umbrella pass に使います
- 背骨は 1 本の waterfall pass のままにし、surface ごとの差分を `schedule.md` の stage owner と write scope で切ります
- Gate 0-1 では `project_reviewer` を intake gate として使い、repo-wide completeness と collision risk を確認します
- Gate 3 では `Single Writer Worktree:`、`Additional Writer Worktrees:`、`Integration Order:` を必ず固定します
- Gate 5-7 では `docs_workflow_steward` を canon docs 整理に使いますが、実装 worker と兼務させません
- Gate 8-9 では言語差分に応じて `python_reviewer` や `cpp_reviewer` と `project_reviewer` を通し、slice 単位ではなく全体整合を見ます
- 同一 worktree では `worker` だけが repo file を編集します
- 複数 writer が必要な場合は、writer ごとに worktree を分けてから統合します

## 8. reuse-first の必須ルール

- まず既存 module、既存 helper、既存 abstraction を探します
- 既存 API shape、命名、error handling、test style、docs style を優先します
- 新しい pattern を導入するときは、詳細設計文書に既存 pattern では足りない理由を書きます
- 新しい identifier や path は worker の自由裁量にせず、詳細設計の naming plan または明白な局所 precedent に結び付けます
- 既存コードを踏襲できるなら、完全新規実装を選びません

## 9. closeout の必須項目

- 実行した validation
- 未実行 validation と理由
- 更新した repo 正本
- commit hash
- push の成否

## 関連正本

- [agents/TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
- [agents/canonical/CODEX_WORKFLOW.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_WORKFLOW.md)
- [agents/workflows/README.md](/mnt/l/workspace/project_template/agents/workflows/README.md)
- [agents/workflows/research-workflow.md](/mnt/l/workspace/project_template/agents/workflows/research-workflow.md)
- [agents/workflows/experiment-workflow.md](/mnt/l/workspace/project_template/agents/workflows/experiment-workflow.md)
- [agents/workflows/workflow-references.md](/mnt/l/workspace/project_template/agents/workflows/workflow-references.md)
