<!--
@dependency-start
contract reference
responsibility Documents the repository-topic clone lifecycle command.
upstream design ../rule/repository-topic-clone.md generic repository-topic clone policy
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace boundary
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/repository_topic_clone.rs lifecycle implementation
downstream implementation ../../tests/agent_tools/test_repository_topic_clone.py validates cleanup and merge gates
@dependency-end
-->

# repository-topic-clone

`tools/bin/agent-canon repository-topic-clone` は、`repository-topic` checkout の
`workspace/<topic>/<repo>` 形 lifecycle を管理する native command です。詳細責務と
clause は
[`documents/rule/repository-topic-clone.md`](../rule/repository-topic-clone.md)
を参照します。

## 基本操作

```bash
tools/bin/agent-canon repository-topic-clone prepare \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone>

tools/bin/agent-canon repository-topic-clone merge-main \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone>

tools/bin/agent-canon repository-topic-clone verify-publication \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  --candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]

tools/bin/agent-canon repository-topic-clone cleanup \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

`<parent-root>` は [事前条件](../rule/repository-topic-clone.md#事前条件) で照合する Git toplevel です。
`--checkout-mode` の選択は [Checkout mode](../rule/repository-topic-clone.md#checkout-mode) に従います。
command は selected checkout の exact path、URL、branch、Git marker と actual Git facts を確認します。
dirty/staged/untracked state はそのまま保持し、prepare/merge/cleanup を拒否します。

作成・再利用・merge の authority は
[clone ライフサイクル](../rule/repository-topic-clone.md#clone-ライフサイクル)、
復元可能性・marker・任意 publication evidence・削除可否は
[クリーンアップ](../rule/repository-topic-clone.md#クリーンアップ) を確認してから操作します。
`cleanup --apply` の前に task owner が exact path の所有と利用終了を確認します。
利用中の agent / process / container mount / runtime 入力、または所有・使用状態が不明な対象は保持します。
必要な利用停止・mount 解除の完了と、保持する ignored / untracked / local-only refs・commits /
submodule / annex content の削除対象外への保存・復元可能性を既存 owner で確認してから実行します。
CLI の clean-status proof はこの利用終了や ignored content・submodule Git metadata/object の保全を証明しません。
linked cleanup は local topic branch を保持します。成功時は exact path の不存在と
`git worktree list` からの消失を確認し、branch 削除は既存 owner の別 operation として扱います。
`merge-main` の成功結果は ancestor proof を返します。
dependency adapter の `status` は [dependency-module-change](dependency_module_change.md) の
read-only path projection であり、directory を作りません。

## 競合の再開

`merge-main` が競合した場合は native Git の merge state と index stages を残して停止します。
integration executor が source owner と実競合をレビュー・解消した後、
[規約の競合の再開](../rule/repository-topic-clone.md#競合の再開) に従って確定します。

```bash
tools/bin/agent-canon repository-topic-clone finalize-merge \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> \
  --checkout-mode <linked-worktree|independent-clone>
```

`finalize-merge` は native Git index の未解決 entry を拒否し、resolved index tree と
`MERGE_HEAD` に基づく commit parents/tree を read back します。
