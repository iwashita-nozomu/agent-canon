# GitHub status lifecycle

<!--
@dependency-start
contract agent-runtime
responsibility Defines Issue status-label reconciliation using ordinary evidence comments and native GitHub identities.
upstream design ../../documents/conventions/software-engineering-principles.md correctness, ownership, failure, and traceability
upstream design ../../documents/operations/issue-label-taxonomy.toml repository label mapping
downstream design ../skills/pr-processing.md invokes this routine inside the publication boundary
downstream implementation ../../.codex/personal/skills/_github-status-lifecycle/SKILL.md private runtime adapter
downstream implementation ../../tools/repository/github/github_status_lifecycle.py transport and reconciliation
@dependency-end
-->

## Reader Map

`pr-processing` が対象 Issue、公開する内容、現在の事実、書込権限、公開結果を所有します。
この routine は、その事実に対応する status、選択されたコメントの確認、単一ラベルの
変更順序と読戻しを所有します。別の taxonomy、publisher、承認段階を作りません。

## Activation Gate

repository-changing work に対応する Issue が確定し、ユーザー依頼または repository
policy が status 更新を要求し、呼出元が対象と書込権限を確認した場合だけ使います。
通常の読取・レビュー・triage・taxonomy 設計だけでは起動しません。
Issue や label の推測・新規作成、PR merge、Issue close はこの操作に含めません。

## Responsibility Boundary

| 対象 | 所有者 |
| --- | --- |
| 対象 Issue/PR、現在の実装・検証事実、公開権限 | `pr-processing` と変更・検証の各 owner |
| ラベル名と明示された旧ラベル | `documents/operations/issue-label-taxonomy.toml` |
| 作業状態の分類、変更順、結果判定 | この routine |
| native comment/Issue ID、単一 API 操作と読戻し | `GhStatusAdapter` と既存 `github_publish.py` transport |
| 説明の十分性、根拠・検証・残件、最終公開報告 | 呼出元の既存 writing/publication owner |

コメントの文面・リンク・モデルから書込権限を推論しません。呼出元は routine の結果を
利用し、同じ状態遷移や成功判定を二重実装しません。

## Canonical label mapping

既存 TOML の `[status_lifecycle]` が `active`、`ready_for_review`、
`needs_verification` の名前を所有します。`legacy_aliases` に宣言された旧ラベルだけを
管理対象へ加えます。標準 `tomllib`（既存 Python 3.10 経路では `tomli`）を使います。
空・重複・衝突・未知キーは拒否し、canonical labels の remote catalog での存在を確認します。
不足するラベルを勝手に作成・rename しません。旧ラベルの不存在は問題にせず、他のラベルは保存します。

## Lifecycle Model

| 状態 | 現在の事実 | 付ける canonical labels |
| --- | --- | --- |
| `active` | 実装・必要な修正を作業中、引継ぎ未準備、または対象検証が失敗 | `active` |
| `review-ready` | 変更と選択した検証が完了し、引継ぎ可能 | `ready_for_review` |
| `review-ready-unverified` | 引継ぎ可能な変更と実行可能な検証を終え、外部制約で必要な検証を実行できない | `ready_for_review` と `needs_verification` |

未修正の実装不良・対象テストの失敗を、外部の検証不能へ言い換えません。
`needs_verification` は単独で使わず、未実施の性質、実際の試行・観測、必要な外部条件、
次の担当・正規経路を通常の説明に残します。専用の必須フィールドや対象外 token は要求しません。
記録が非空であることだけでは内容の正しさを保証できないため、内容は owner が確認します。

## Evidence Comment Contract

結果は通常の Markdown で残します。変更範囲と理由、実在する branch/commit/PR、
実施した検証と未実施事項、残件と次の担当が、私的な会話なしで追える説明にします。
PR がない段階では PR identity を作らず、存在する source・Issue・作業結果だけを記録します。
書式を満たすための marker、hash、canonical serialization、全履歴の同一 payload 件数は不要です。

`reconcile_status` へは、投稿する `comment_body` または再利用する `comment_id` の
どちらか一つを渡します。既存コメントを使う際は、呼出元が内容と対象の適合を確認して
その native ID を明示します。同文の別コメントが存在してもそれだけでは拒否せず、
逆に同文検索から操作の完了・排他・再投稿権限を推論しません。

新規投稿は一回だけです。GitHub の応答から comment ID を取得し、その ID を再取得して
`issue_url`、本文、公開 URL を確認します。既存 ID も同じ対象 Issue への所属を確認します。
応答不明・ID 不明・取得失敗では停止し、POST を盲目的に繰り返しません。受付後に応答を
失った場合は、呼出元が既存 remote 状態を確認し、特定できたコメントを明示して再開します。
過去のコメントを自動編集・削除しません。

## Reconciliation Algorithm

1. 呼出元が対象・権限・作業事実・説明を確定します。taxonomy と native repository label
   catalog を照合し、変更前の Issue labels を取得します。
2. 事実から必要なラベル集合 `D` を決め、通常コメントを一度投稿して読戻すか、指定 ID を
   読みます。証拠の保存とラベル更新を一つの GitHub transaction と称しません。
3. `M = canonical labels ∪ declared aliases` とし、現在の `M` 内で不要なラベルを削除し、
   不足する canonical labels だけを追加します。full-label replacement は使いません。
4. 各操作の直前に全 labels が直前の期待状態と同じか確認し、単一 POST/DELETE を一度
   実行して、その直後の全 labels を読み戻します。観測した変更・応答不明・不一致では
   完了済み操作と既知の結果を残して停止します。
5. 最後に Issue と選択した comment ID を読み、管理対象が `D` と一致すること、旧ラベルが
   残らないこと、他のラベルが保存されたこと、選択コメントの所属と内容が変わっていないことを確認します。

確認するのは選択した一件の native identity であり、全コメント履歴の一意性ではありません。
GitHub の読取と書込の間の競合や、観測されなかった `A -> B -> A` は排除できません。
コメントの private hash は CAS を提供しないため、独自 digest を増やしてその保証を装いません。

## Failure Semantics

実装は失敗に `code_owner` と `responsibility_scope` を付け、API transport の失敗と
lifecycle の入力・状態不整合を区別します。コメント所属/内容の不一致、取得不能、label
catalog の不足、観測した label drift、部分的な変更を成功や警告だけに変換しません。

部分失敗では完了した操作、失敗/応答不明の操作、取得できた現在 labels、意図した labels、
選択した comment ID を残します。追加読取にも失敗した場合は現在値を不明と明示します。
自動 rollback は別の競合を起こし得るため行わず、同じ API write を盲目的に再試行しません。
次の owner が fresh remote 状態から必要な操作だけを選びます。

## Completion Output

成功結果は lifecycle、変更前後の managed labels、追加・削除した labels、完了操作、
native comment ID/URL、最終 Issue readback を返します。コメント本文と結果の意味は
チャットと Issue の両方へ引き継ぎます。ラベル更新成功は実装・検証・merge の成功証拠ではありません。
