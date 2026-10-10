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

repository-topic checkout の lifecycle、normal merge、receipted cleanup を
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
から組み立てます。handoff の identity と current owner evidence を引き継ぎ、write-capable な `prepare` には
current allowed paths を渡します。`owner-evidence` digest は承認ではなく lifecycle metadata です。
computed path と actual Git identity が一致する checkout の task marker / writer packet は
`prepare` で current metadata へ更新できます。
この metadata-only operation は source と Git index を変更せず、dirty status を clean 扱いしません。
source discovery の `prepare` は writer scope 確定前でも可能で、その場合 packet は作られません。
scope 確定後は同じ exact Git identity で再prepareし、current allowed paths を packet にします。
`cleanup` は current Git identity を確認し、marker が存在する場合は marker と current evidence の一致も要求します。

| 操作 | 実行前に読む正本 |
| --- | --- |
| `prepare` | [事前条件と Checkout mode](../../documents/rule/repository-topic-clone.md#事前条件)、[作成・再利用と writer packet](../../documents/rule/repository-topic-clone.md#clone-ライフサイクル) |
| `merge-main` | [事前条件](../../documents/rule/repository-topic-clone.md#事前条件)、[merge と authority](../../documents/rule/repository-topic-clone.md#clone-ライフサイクル) |
| `finalize-merge` | [競合の再開条件](../../documents/rule/repository-topic-clone.md#競合の再開) と [確定コマンド](../../documents/tools/repository_topic_clone.md#競合の再開) |
| `cleanup`（不要になった時点） | [起動・保持判断と復元可能性・削除条件](../../documents/rule/repository-topic-clone.md#クリーンアップ) |

`linked-worktree` の `cleanup --apply` は request の exact worktree/topic path を回収しますが、
local topic branch は保持します。実行前に task owner が ignored / untracked / submodule / annex-only content を
削除対象外へ保存したことを確認します。CLI の status と local superproject head はその内容の復元可能性を証明しません。
branch の削除権限をこの lifecycle に追加せず、既存の cleanup authority と復旧可能性の契約をそのまま適用します。

操作結果を read back し、失敗時は
[例外/フォールバック](../../documents/rule/repository-topic-clone.md#例外フォールバック)
に従って次の操作または状態保持を判断します。
