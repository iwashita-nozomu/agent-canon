# GitHub connected work

<!--
@dependency-start
contract workflow
responsibility Adapts existing repository-work owners to authorized GitHub tools in the current session without requiring a local execution environment.
upstream design chatgpt-codex-routing.md execution admission and explicit session constraints
upstream design ../skills/pr-processing.md publication authority, integration, and readback owner
upstream design ../../documents/operations/BRANCH_SCOPE.md branch scope and dependency-closed commit owner
upstream design github-status-lifecycle.md Issue status and evidence owner
downstream design ../skills/pr-processing.md exposes this routine through the existing public skill
@dependency-end
-->

## Use and boundary

ChatGPT などの現在セッションから、認可済み GitHub 接続で Issue 作業を進めるときに
`$pr-processing` が読む transport 手順です。例: `$pr-processing この環境の GitHub
接続で owner/repository の Issue を修正し、PR まで公開する`。
実装判断は変更箇所の owner、branch は [BRANCH_SCOPE](../../documents/operations/BRANCH_SCOPE.md)、
公開は [pr-processing](../skills/pr-processing.md)、status は
[github-status-lifecycle](github-status-lifecycle.md) に残します。新しい public skill、
publisher、承認段階、全環境共通の capability 検査は追加しません。

## 1. Resolve the operation, then use the available connection

要求された成果物、対象 repository / Issue、変更範囲、必要な evidence を固定します。
remote に存在する source だけで足りる作業と、local/uncommitted state や実行環境が必要な作業を
分けます。後者を「remote に存在しないから不要」と扱いません。

現在セッションの tool discovery で必要な GitHub action の schema を読み、実際の
read で接続と対象を確認します。`api_tool` がある環境では `list_resources` から
GitHub の必要な action を取得して呼びます。action 名、引数、対応 URL は発見した
schema を正本とし、別セッションの名前や汎用 fetch の対応範囲を推測しません。
既に十分な read があれば重複確認せず、write 可否の dummy Issue / commit は作りません。

接続が使えるなら、ローカル `git`、`gh`、Docker、GPU、network の事前整備を要求しません。
Git の DNS 失敗は connector の失敗ではありません。同じ失敗を反復せず、必要な
operation が実行できる transport を使います。認証・承認・接続の追加が必要と判明した
場合はその境界で止め、token の探索、無断インストール、別 credential で迂回しません。

## 2. Read the owner and establish the work branch

repository metadata と最新 main の SHA を読み、その SHA に固定して `AGENTS.md`、
明示参照された共通 base、対象 subtree の instructions、選択 owner、変更対象と
必要な caller / consumer を読みます。検索 index や会話履歴だけを current source に
しません。参照を辿るのは変更契約に必要な範囲だけとし、全 repo / 全 PR 走査は不要です。

関連 Issue と active branch / PR を照合します。既存の対応先を再利用し、新規 Issue
は要求または repository policy が起票を許可する場合だけ、実際の scope と根拠を
書いて作成します。repository-qualified identity と status は既存 owner に従います。

編集前に最新 main から Issue 番号入り branch を作るか、関連 active branch へ最新
main を取り込みます。branch の実 SHA と main を比較し、同一または包含済みなら
merge は no-op と記録します。無意味な merge commit は作りません。差分があれば、
発見済みの branch 統合 action または正規の Git 実行環境で実際に統合します。
PR を main へ merge する action は、この向きの branch 統合の代替ではありません。

競合時は publication owner の保存・解決手順を使います。必要な merge-base、双方の
内容、解決根拠と readback を取得できない transport では解決済みとしません。
古い tree に main を追加 parent として付けるだけの疑似 merge、`ours` / `theirs` の
全体採用、force update で統合を偽装しません。未解決部分を保持し、進められる独立作業と
Issue への引継ぎは続けます。

## 3. Edit and publish one coherent unit

取得した完全な file bytes と blob SHA を基準に、変更 owner の手順で編集します。
分割・切詰めされた tool 応答を全内容として書き戻しません。ローカルへ一部 source を
保存しただけなら「部分 source」であり、完全 checkout や user の dirty state では
ありません。解析用の状態や生成物を repository の tracked path に混ぜません。

一つの契約を作る複数ファイルは、Git data actions が使える場合、現在の branch
commit の完全な tree を `base_tree` として変更 path だけ重ね、同じ parent の一つの
commit にします。未変更 path、mode、symlink、gitlink を保存し、全 tree を空から
再構築しません。独立した単一ファイルなら、その branch と最新 blob SHA を指定する
contents action でも構いません。必須の相互参照をファイル別 commit に分断しません。

ref 更新直前に branch head を再読し、観測した parent との一致を確認して
non-force update を行います。head が動いたら fresh diff から計画を更新します。
read と write は原子的ではなく、`force=false` も CAS ではありません。成功後は
remote head / tree / diff を読み、作成した commit と scope が一致することを確認します。
応答不明なら先に remote state を読み、create や update を盲目的に再送しません。

## 4. Validate what can actually be observed

変更契約の既存検証を選び、exact source / head、command または action、結果と証明した
範囲を残します。完全 checkout の canonical validation、部分 source の構造・差分確認、
remote readback、hosted checks を区別します。CI の緑だけで対象外・skipped の検証を
実施済みにせず、run / job / step と対象 SHA を確認します。

実行環境がない検証は未実施とし、必要な property、理由、実際の試行と結果、次の owner
と正確な検証経路を Issue に残します。検証のためだけの Docker/GPU 設定変更、新 checker、
無関係な全 suite は追加しません。変更自体の不良や失敗した検証を環境制約へ付け替えず、
必要な修正は同じ範囲で続けます。安全に公開可能な差分まで止める理由にはしませんが、
未検証の公開を validation complete や merge-ready と呼びません。

## 5. Refresh main, publish the PR, and leave a durable handoff

PR の作成・更新前に最新 main と branch を再読し、必要な実統合・競合解決・影響範囲の
再検証を行います。既存の同じ head/base の PR を再利用し、なければ認可済みの PR 作成を
実行します。統合不能や作業未完了なら通常の完了 PR とせず、公開可能な draft PR または
既存 branch / commit と具体的な阻害要因を Issue に残します。PR 作成を main への merge、
Issue close、実環境への適用と同一視しません。

最後に PR と Issue を再読します。Issue コメントには成果の意味、判断根拠、変更範囲と
非目標、branch / base / exact head / PR、実施検証と残件、次の owner/action を、チャットと
同程度に判断可能な内容で残します。PR が作れない場合も、成果または未公開差分の実在する
保存先と停止理由をコメントします。リンクだけで結果説明を代替しません。

status の意味と順序は既存 lifecycle / taxonomy をそのまま用い、発見した単一 label
追加・削除 action と readback で適用します。無関係な label の全置換はしません。
最後の報告は「実装・検証・公開・適用」を分け、現在の状態を述べます。この文書を読んだ
ことを ChatGPT への永続インストール、自動 discovery、実際の Codex 起動、または後で
非同期に実行する約束として扱いません。
