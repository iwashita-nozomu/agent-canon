# 実装ウォーターフォールワークフロー

この文書は、repo に変更を入れる実装プロセスを、段階ゲート付きのウォーターフォールとして進めるための正本です。
対象は `python/`、`documents/`、`agents/`、`docker/`、`scripts/` など、repo に持ち帰る変更全般です。

この repo では workflow family の選択は `agents/TASK_WORKFLOWS.md` を使いますが、実装そのものの進め方はこの文書を共通ルールにします。

## 1. 目的

- stage ごとに適切な subagent / specialist を explicit に立てる
- 要件が固まる前に code を書き始めない
- 計画が固まる前に詳細設計へ進まない
- 詳細設計が固まる前に実装を広げない
- 実装、review、verification を段階ゲートで区切る
- 各 pass で複数回の独立レビューを必須にする
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
1. 実装
1. 実装 checkpoint review
1. 最終受け入れ review
1. audit / gate close

`Scoped Change` のような小さい差分でも、実行計画、計画レビュー、詳細設計、詳細設計レビューを省略しません。
また、`計画レビュー` と `詳細設計レビュー` は別エージェントで行います。とくに `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします。

### Gate 0. Subagent Bootstrap

目的:
- run bundle と review artifact を先に固定する
- 要件 reviewer、計画 reviewer、詳細設計 reviewer を別 agent instance として割り当てる

最低限の記録:
- `team_manifest.yaml`
- `intent_brief.md`
- `decision_log.md`

推奨 subagent:
- repo 内調査が要る場合は `explorer`
- 文書主体の整理が要る場合は `docs_workflow_steward`

必須ルール:
- repo-changing task では explicit subagent activation を省略しません
- `計画レビュー` と `詳細設計レビュー` は別 agent instance で行います
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします

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

主担当:
- `manager`
- `manager_reviewer`

推奨 subagent:
- repo survey が要る場合は `explorer`

必須レビュー:
- `manager_reviewer`
  - scope、non-goals、acceptance criteria、validation plan の粗さを確認する
  - family 選択が妥当か確認する

exit 条件:
- 何をもって完了とするかが 1 文で言える
- どの family で扱うかが決まっている
- 実装前に必要な review / validation が決まっている
- requirements review が `resolved` になっている

### Gate 2. 調査

目的:
- 既存コード、既存 docs、外部根拠、既存 implementation pattern を調べる

主担当:
- 必要に応じて `researcher`
- 必要に応じて `research_reviewer`

推奨 subagent:
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

推奨 subagent:
- 文書主体なら `docs_workflow_steward`

必須レビュー:
- ここでは plan review は行いません。次 gate で独立 reviewer に渡します。

ルール:
- 実行計画は詳細設計の前に必ず確定させます
- どの subagent / role がどの stage を担当するか明記します

exit 条件:
- `schedule.md` に stage 順序、担当 agent、exit criteria、validation が書かれている
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

推奨 subagent:
- `reviewer`

必須レビュー:
- `schedule_reviewer`
  - stage 順序、依存関係、review agent の分離、rollback point を確認する
- 必要に応じて `infra_reviewer`
  - runtime、CI、Docker、dependency 影響が計画に反映されているか確認する

ルール:
- 計画レビュー agent を詳細設計レビュー agent と兼務させません
- stage の飛ばしや merge は認めません

exit 条件:
- `schedule_review.md` が `resolved` になっている

### Gate 5. 詳細設計

目的:
- 実装前提を十分に伝える詳細設計文書を起こす
- 既存コードと既存の書き方をどう踏襲するかを明文化する

主担当:
- `designer`

推奨 subagent:
- 文書主体なら `docs_workflow_steward`
- 既存 code path 調査が要る場合は `explorer`

最低限の記録:
- `Existing Code And Docs To Reuse:`
- `Patterns And Writing Style To Mirror:`
- `File-By-File Design:`
- `Interfaces And Boundaries:`
- `Validation And Rollback Plan:`

ルール:
- 詳細設計の目標は、実装前に読むべき文書を完成させることです
- 既存 module boundary、命名、API shape、test style、docs style から逸脱する場合は、理由を明示します

exit 条件:
- 実装者が文書だけ読んで着手できる
- 新規 abstraction より reuse-first の方針が説明できる

### Gate 6. 詳細設計レビュー

目的:
- 詳細設計文書の十分性と、reuse-first / style-following が担保されているか確認する

主担当:
- `design_reviewer`
- 必要に応じて `infra_reviewer`

推奨 subagent:
- `reviewer`
- Python 差分が中心なら追加で `python_reviewer`
- repo-wide 影響が大きければ `project_reviewer`

必須レビュー:
- `design_reviewer`
  - 文書 completeness、実装可能性、既存コード再利用、既存の書き方踏襲、不要な新規性を確認する
- 必要に応じて `infra_reviewer`
  - infra / runtime 影響が設計文書に落ちているか確認する

ルール:
- `詳細設計レビュー` は計画レビューより重い gate とします
- design reviewer が未解消の懸念を残したまま実装へ進みません

exit 条件:
- `design_review.md` が `resolved` になっている
- reuse-first と style-following の懸念が解消している

### Gate 7. 実装

目的:
- 凍結済みの設計を実装へ落とす

主担当:
- `implementer`

推奨 subagent:
- bounded な切り出しだけを `worker` に渡す

ルール:
- 実装は 1 つの change request に閉じます
- docs と tests は同じ pass で更新します
- 途中で scope を広げません
- 設計を変えたくなったら Gate 5-6 を開き直します
- 非自明な変更では、final polish 前に checkpoint review を必ず 1 回挟みます
- 既存コード、既存 helper、既存 naming、既存 test style、既存 docs style を優先します
- 完全な新規実装より、既存実装の拡張、既存 pattern の模倣、既存 file layout の踏襲を優先します

必須レビュー:
- `change_reviewer`
  - implementation checkpoint review として、構造、境界、明白な回帰、設計逸脱を早期に確認する
  - `Large Delivery` では chunk ごとに最低 1 回
  - `Platform And Environment` では rollout 影響が見える時点で最低 1 回

exit 条件:
- 差分が requirements / plan / design に一致している
- planned checks を実行できる状態になっている
- implementation checkpoint review が `resolved` になっている

### Gate 8. 最終受け入れ review

目的:
- 差分が設計どおりで、回帰やリスクが許容範囲に収まっているか確認する

主担当:
- `final_reviewer`
- 必要に応じて `python-review`
- 必要に応じて `md-style-check`
- 必要に応じて `critical-review`

最低限の確認:
- code / docs diff review
- validation plan の実行
- security / safety / provenance の確認

必須レビュー:
- `final_reviewer`
  - 変更全体、docs 同期、受け入れ条件達成、不要な新規 pattern の混入有無を確認する
- 必要に応じて `python-review`
  - Python API、型境界、test coverage の不足を確認する
- 必要に応じて `md-style-check`
  - 文書体裁とリンク整合を確認する
- 必要に応じて `critical-review`
  - claim、evidence、overclaim を確認する

ルール:
- 設計を変えない軽微修正だけは、この gate 内で戻して構いません
- 新しい requirement が必要なら Gate 1 に戻します
- 計画変更が必要なら Gate 3 に戻します
- 設計変更が必要なら Gate 5 に戻します

exit 条件:
- `required_change` が解消している
- 実行した checks と未実行理由が説明できる
- final acceptance review が `resolved` になっている

### Gate 9. Audit And Gate Closure

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

必須レビュー:
- `auditor`
  - required reviews が揃っているか、artifact と closeout evidence が欠けていないか確認する

exit 条件:
- auditor review が `resolved` になっている
- verifier が gate を閉じている

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
  - Gate 6 に戻して修正する
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

- Gate 0 から Gate 8 をそのまま 1 pass で通します
- artifact は軽くて構いませんが、要件整理、計画、詳細設計、各 review の区別は崩しません
- `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer` を軽量版として必ず有効化します

### Research-Driven Change

- literature survey、baseline run、比較設計は Gate 0-5 の入力です
- 1 回の code change は 1 回の waterfall pass で実装します
- `rerun_required` や新仮説が出たら、新しい pass としてやり直します

### Large Delivery

- `scheduler` が chunk を先に固定します
- 各 chunk は独立した waterfall pass として閉じます
- chunk 間の横断変更は、次 chunk の Gate 1 に持ち越します
- 各 chunk の前に詳細設計文書を起こし、詳細設計レビューを通します
- 各 chunk で checkpoint review を複数回に増やして構いません

### Platform And Environment

- Gate 2-5 で rollout / rollback / environment impact を必ず固定します
- Gate 7-8 で `docker/`、CI、runtime pack、関連 README の同期を確認します
- `infra_reviewer` は詳細設計レビューだけでなく最終受け入れ review にも参加して構いません

## 8. reuse-first の必須ルール

- まず既存 module、既存 helper、既存 abstraction を探します
- 既存 API shape、命名、error handling、test style、docs style を優先します
- 新しい pattern を導入するときは、詳細設計文書に既存 pattern では足りない理由を書きます
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
- [documents/WORKFLOW_GUIDE.md](/mnt/l/workspace/project_template/documents/WORKFLOW_GUIDE.md)
- [documents/research-workflow.md](/mnt/l/workspace/project_template/documents/research-workflow.md)
- [documents/experiment-workflow.md](/mnt/l/workspace/project_template/documents/experiment-workflow.md)
- [documents/workflow-references.md](/mnt/l/workspace/project_template/documents/workflow-references.md)
