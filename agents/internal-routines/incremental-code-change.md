# 依存順走査による逐次コード変更

<!--
@dependency-start
contract workflow
responsibility Connects bounded coverage traversal, incremental repair, evidence invalidation, and dependency-complete commit boundaries without a second workflow engine.
downstream design ../skills/code-cleanup.md consumes the shared asset universe and streaming semantic cleanup
upstream design ../skills/dependency-analysis.md owns dependency discovery and the Change Impact Packet
upstream design ../skills/refactor-loop.md owns behavior-preserving repair batches and selected validation
upstream design ../../documents/operations/BRANCH_SCOPE.md owns dependency-complete commit planning and exact-tree validation
upstream design ../skills/change-review.md owns independent review and focused rechecks
upstream design ../COMMUNICATION_PROTOCOL.md owns bounded handoff and context reuse
upstream design ../skills/tokens.md owns measured token-efficiency claims
upstream design github-status-lifecycle.md owns Issue and PR status readback
downstream design README.md indexes this internal workflow
@dependency-end
-->

## 選択と責務

全対象の走査と逐次修正、またはタスク内の重複読取・引継ぎ・再レビューの修正を
依頼されたとき、`code-cleanup` の Route から選択する内部手順です。通常の局所修正に
全走査を追加しません。既存の `dependency-analysis -> refactor-loop -> change-review`
を使い、スキル選択、writer数、検証コマンド、Git操作の権限を再定義しません。

入口の指定例: 「`code-cleanup`で、対象Issueの責務を依存順に走査し、逐次更新する。
対象外の改善は混ぜず、依存が閉じて検証できた単位でコミットする」。以下の順に進めます。

## 1. 網羅する範囲を固定する

Issue、repository、base SHA、branch、既存のdirty状態、対象契約と検証方法を一度確認します。
最新main起点または関連アクティブbranchを使い、branch名にIssue番号を含めます。
対象pathは候補であり、owner、利用側、設定、登録、生成物、tests/docsまでの必要な
依存を既存の解析経路で辿って、変更可能な責務単位と読取だけの境界を決めます。
未変更の利用側も対象です。全repo走査を依頼された場合は、変更ファイルだけを母集団にしません。

まずGitのpath一覧を作り、本文は必要な単位から読みます。次は既存Git ownerが許可した
checkoutで使う読取例です。`scope`は確認済みの対象path、`before`は直前に照合したcommitです。

```bash
git ls-files --stage -z -- "$scope"                # indexのpath/mode/blob
git diff --name-status -z --find-renames "$before" -- "$scope"
git ls-files --others --exclude-standard -z -- "$scope"
```

一覧は既存の外部作業領域に保持し、全件を会話や子promptへ展開しません。indexのblobは
未stageの内容を表さないため、dirtyな対象は実際に読んだ内容と区別します。NUL区切りを
維持し、改行・空白を含むpathを行分割しません。ignored/generated/annex payload、
submodule、外部repositoryの扱いは明示し、必要な入力をignoreだけで除外しません。
秘密や無関係な実験ログを読む必要はありません。対象外の理由は既存範囲表にまとめます。

既存の `reuse_survey` / `Change Impact Packet` / Issue範囲表を更新して使います。
新しい台帳は作らず、単位、読取根拠と版、次に読む位置、判断、検証・commit参照が辿れば十分です。
各行の読了receipt、全機能の不使用記録、同じ本文の複数投影は作りません。

## 2. 読取順とコミット順を分ける

最初の読取は「利用側が必要とする契約 -> 正本owner -> 影響する利用側」です。
これは全履歴の調査ではありません。削除・分割で寄与が不明なときだけ関連する旧版を読みます。
修正単位の順序は[コミット計画の正本](../../documents/operations/BRANCH_SCOPE.md)に従います。

- 前提単位が完了してから依存する単位へ進みます。同時に変えないと契約が壊れる組は
  同一単位にまとめ、循環する変更依存は強連結成分として扱います。単なる同一fileではまとめません。
- 依存上同順位なら既存のowner/path順、単位内では定義・節の出現順を使います。
  独立した単位は並行実行可能ですが、この手順だけで子を増やしません。
- 既存 `refactor-loop` が共有構造の利用側完成形を先に決める場合はその順序を維持します。
  内部編集の各段階を別commitにする意味ではありません。互換性のないAPIとcaller、
  schemaと設定、生成元と同期が必要なtracked生成物は一つの検証可能なcommitに閉じます。

全fileの詳細計画ができるまで修正を待ちません。着手する単位の必須依存が未解決なら、
まずその依存だけを調査します。無関係な独立単位まで止めず、別Issueの完了を形式的な前提にしません。

## 3. 読んだ範囲で修正し、影響だけ戻す

作業中の集合を、対象単位 `U`、未走査 `P`、既読だが根拠が失効した再確認 `R`、
現行根拠で処理済み `C` と呼びます。これは既存作業記録の見方であり、保存schemaではありません。
未解決の必須依存・読取不能・検証不能は理由付きで残し、処理済みにしません。

1. 依存が準備できた `R` または `P` の単位を選び、必要な定義・節だけ読みます。
   意味、入力、出力、副作用、呼出元への寄与を確認し、保持・修正・削除を判断します。
   寄与と影響が閉じたblockは同じpassで修正し、全文監査の後に編集をやり直しません。
2. 修正後の差分を確認し、新規path、削除、rename、依存・設定・生成規則の変化を
   既存の依存根拠へ反映します。新しく見つかった必要対象は `U` と `P` に追加します。
   削除対象は一覧から黙って消さず、旧責務の保存・委譲・認可された廃止を記録します。
3. 変更箇所に依存していた判断・利用側・tests/docs/生成物のうち、既読のものだけを
   `C` から `R` に戻します。未走査のものは `P` に残します。変更前後両方の依存を使い、
   削除で消えたedgeやrename前の利用側を取り落としません。
4. 修正した単位自体も新しい内容・影響範囲を照合してから処理済みにします。
   新しいedgeが同時変更を要求すれば、次の編集・commitの前に単位を統合し順序を更新します。
   手元の一箇所だけで閉じたと見なして利用側を後のcommitへ送ってはいけません。
5. 位置はpathと定義/節、読んだ内容の版で辿ります。前方の挿入・削除後に古い行番号から
   再開せず、差分と現在の定義位置で未走査範囲を再配置します。対応が曖昧ならそのfile内の
   必要範囲を読み直し、無関係な全repoの再走査へ戻しません。

依存edgeを `a -> b` =「bの判断がaに依存する」とすると、変更集合 `D` の保守的な
影響候補は `D ∪ reachable(G_before ∪ G_after, D)` です。全graphの本文を作り直さず、
既存toolの依存根拠からこの候補を辿り、判断が本当に依存する範囲を確認します。
path追加・削除自体に依存するglob、登録一覧、生成規則、検証selectorも入力に含めます。
動的参照やselectorの範囲が証明できないときは最小の既知subsystemまで広げて確認し、
それでも不明なら該当単位を未解決にします。検索でヒットしないことは「依存なし」の証明ではありません。

## 4. 記録と引継ぎは現行状態と差分だけ更新する

現在有効な契約と判断は既存の正本/packet一か所で解決できるよう更新します。
過去の証拠は保持しますが、「最新差分 -> 前版 -> さらに前版」を全部読まないと
現行契約が分からない状態を引継ぎません。保持・置換した要求IDと現行の参照先を示し、
過去の承認を新しい契約への承認に読み替えません。

継続するwriter/reviewerには、現在の対象identity、変更点、影響する要求と対象範囲、
未解決事項、選択した検証、正本参照を渡します。既知の全文をroute/request/reviewへ
重複して転記しません。新しい担当者には判断に必要な正本の定義・節を渡し、参照を
解決できなければ不足分を取得します。短い要約で権限・意味・failure semanticsを置き換えません。

同じ入力と判断への探索・評価を再開しません。既存review ownerの最初のレビューと、
変更で失効した指摘・証拠の再確認を区別します。hash変更だけで全判断を破棄することも、
本文不変だけで設定・依存の変更を無視することもしません。未知の影響は明示して選択ownerに戻します。
出力は必要な範囲・結果と根拠参照に絞り、切れた全文取得を繰り返さず未読offsetから続けます。

## 5. 責務が閉じた時点で検証してコミットする

逐次修正とcommitは別の境界です。各行・tool呼出・ファイル種別・時間間隔では切りません。
一つの単位について、必要な依存と利用側の追従、選択された検証・レビューが閉じた時点で、
[Commit Correctness Contract](../../documents/operations/BRANCH_SCOPE.md#commit-correctness-contract)
に従ってcommitします。次の独立単位が全て終わるまで保持する必要はありません。

候補index/treeを隔離された既存の検証経路へ渡し、後続commitや未commit/untracked入力を
混ぜないで確認します。検証対象と確定commitのtree一致を読み戻します。各commitの成功は
そのtree・固定入力・検証経路に結び付け、最終HEADでの成功を中間commitへ流用しません。
同じtreeと全検証入力が同一なら既存証拠を対応付け直せますが、同じfile本文だけでは不十分です。
検証はunit境界で選択されたものを実行し、全suiteや計測を各行の必須操作にしません。

失敗時は該当契約を修正し、同じ失敗を新しい根拠なく反復しません。境界が成立しなければ
commit計画を組み直します。実行環境がない場合は未確認の性質とownerを残して
`need verification` とし、合格・修正完了を装いません。引継ぎ用の未検証候補を公開する場合は
Draft PRと未実施理由を明記し、検証済みcommit列として扱いません。user-owned状態は保存します。

pushはcommitと別に、共有・引継ぎ・PR公開の目的と権限から判断します。PR前に最新mainを
読み直し、既存Git ownerの経路で取り込み・競合解決します。base差分と統合差分から
新規対象と失効した根拠だけを `P/R` に戻し、必要な各commitと統合HEADを検証します。
最後にremote head/base、Issueコメント、statusを読み戻します。変更を引き継げる時点で
`in progress`を解除し、`ready for review`、検証不足があれば`need verification`を付けます。

## 6. 網羅性と修正効果を分けて閉じる

対象一覧を最終treeと照合し、新規・削除・移動を反映します。これはpath/identityの差分確認で、
本文の全再読ではありません。`P`と`R`が空で、全対象に現行根拠の処理結果があり、
必須の未解決事項がなければ、このsnapshotの走査は完了です。保留を処理済みに移して
網羅したことにしません。対象外の問題は理由と別ownerを残し、今回の終了条件へ取り込みません。

有限な対象と安定した依存関係では各単位を初回に一度扱い、その後は入力が変わった
判断だけ戻すため、作業量は初回走査と実際の影響再確認の和になります。ただし新規要求・
動的依存・修正の繰り返しが続く場合の一回走査や自動収束は保証しません。同じ根拠で
未解決集合が減らない場合は該当ownerへ原因を返し、回数上限だけで成功にしません。
走査完了、検証合格、PR公開、トークン削減の実測は別判定です。削減率は`tokens`の
同等条件の実測に委譲し、本文bytesや操作数だけから効果を断定しません。

## トークン過剰消費への適用順

実際の依存順を優先し、その制約が同順位なら次の因果順で候補を調べます。今回選択した
要因だけを修正し、全段の実装や別Issueの解決を一律の終了条件にしません。

| 順 | 観測から追う責務 | 修正と検証の単位 |
| --- | --- | --- |
| 1 | 同じ要求を複製するpacket生成元とその利用側 | 現行契約への参照を解決できる生成元・consumer・fixtureを一緒に修正し、要求/権限の欠落と全文複製の双方を確認する |
| 2 | 過去版の連鎖から現在の契約を復元する経路 | 現行状態の生成・読取を揃え、履歴保持と新担当者の必要情報取得を確認する |
| 3 | 変更からreview/validationを再起動する経路 | 変更前後の影響範囲、未変更consumer、selector、独立reviewの保持を確認する |
| 4 | 同じ探索や過大出力を反復する呼出元 | 既知path/範囲と既存toolを使い、不足時の追加取得を確認する。モデル・並列数は原因の観測なしに変えない |

## 手順の検証例

文書レビューでは次の遷移を辿ります。実行時の合格を主張する場合は、実際のtaskか
既存fixtureで同じ性質を観測します。この表は新しい検証engineや全taskの必須チェックリストではありません。

| 入力・変更 | 必要な結果 |
| --- | --- |
| Aに依存する既読Bを残してAを変更、独立Cは不変 | Bだけ再確認へ戻し、Cの本文再読を追加しない |
| APIとcallerが互換性なく変わる、または変更依存が循環する | 同一単位で追従・検証・commitし、片側だけのcommitを作らない |
| 削除/renameで古いedgeが消える | 変更前の利用側も追い、旧責務のdispositionを残す |
| cursorより前に定義を追加、別の新規fileも追加 | 未走査範囲を再配置し、新規対象を一覧へ追加する |
| file本文は不変だがconfig/glob/生成規則が変化 | 影響する判断・selector・検証を失効させる |
| 動的参照が不明、または必須検証が実行不能 | 該当単位を未解決として残し、走査・検証成功を宣言しない |
| 全入力が不変、同じ指摘への追加応答だけが来る | 有効な根拠を再利用し、広域検索・レビューを再開しない |
| mainに対象consumer/新規pathが追加される | base/統合差分から対象・影響を更新し、統合済みtreeを検証する |

Gitコマンドの意味は公式の[ls-files](https://git-scm.com/docs/git-ls-files)と
[diff](https://git-scm.com/docs/git-diff)を参照します。scope外の探索、書込、実行は許可しません。
