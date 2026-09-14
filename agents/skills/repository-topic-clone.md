# repository-topic-clone

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for repository-topic checkout operations.
upstream design ../canonical/skills.md skill canon registry
upstream design ../internal-routines/design-implementation-correspondence.md design read/fingerprint/handoff route
upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md topic workspace boundary
downstream implementation ../../tools/repository/workspace/repository_topic_clone.py lifecycle tool
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

repository-topic checkout の lifecycle、normal merge、publish 後の一時 material cleanup を
`workspace/<topic-slug>/<repo-name>` の責務境界で扱います。

## 使用 route

repository-topic checkout の操作を選び、
[適用範囲](../../documents/rule/repository-topic-clone.md#適用範囲) と下表の該当規約を
実行前に読みます。`.gitmodules` の gitlink/pin/projection 判断は
[dependency-module-change](dependency-module-change.md) へ委譲します。
この skill は操作選択を所有し、lifecycle の判断条件を再定義しません。

## 使う command

共通入口は `python3 tools/repository/workspace/repository_topic_clone.py` です。
選択した操作だけを実行し、引数は [CLI 参照](../../documents/tools/repository_topic_clone.md#基本操作)
から組み立てます。handoff の identity と owner evidence を引き継ぎ、`prepare` には allowed paths も渡します。

| 操作 | 実行前に読む正本 |
| --- | --- |
| `prepare` | [事前条件と Checkout mode](../../documents/rule/repository-topic-clone.md#事前条件)、[作成・再利用と writer packet](../../documents/rule/repository-topic-clone.md#clone-ライフサイクル) |
| `merge-main` | [事前条件](../../documents/rule/repository-topic-clone.md#事前条件)、[merge と authority](../../documents/rule/repository-topic-clone.md#clone-ライフサイクル) |
| `finalize-merge` / `resume-merge` | [競合の再開条件](../../documents/rule/repository-topic-clone.md#競合の再開) と [再開コマンド](../../documents/tools/repository_topic_clone.md#競合の再開) |
| `cleanup`（publish/integration 後） | [一時 material の回収](../../documents/rule/repository-topic-clone.md#クリーンアップ) |

`cleanup` は durability を判定する第二ゲートではありません。変更を PR head / integration target へ
反映する責務は publish/integration owner が先に閉じます。その後は canonical lifecycle が作った
checkout を一時 material として回収します。

`linked-worktree` では `cleanup --apply` で worktree/topic path を削除した後、同じ request の
local topic branch も残しません。branch 名は request の exact `--branch` をそのまま使い、
「復旧用」「また使うかもしれない」を理由に保持しません。remote PR branch は open PR の参照先なので
local cleanup の対象外です。merge 後の remote branch cleanup は publication owner の closeout に委譲します。

この local branch cleanup は repository-topic lifecycle が作成・所有した branch に限定します。
shared/unknown branch を探索して消す処理や、cleanup 前に recoverability を再判定する gate は追加しません。

操作結果を read back し、失敗時は
[例外/フォールバック](../../documents/rule/repository-topic-clone.md#例外フォールバック)
に従って次の操作または状態保持を判断します。
