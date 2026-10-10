<!--
@dependency-start
contract reference
responsibility Documents the repository-topic clone lifecycle command.
upstream design ../rule/repository-topic-clone.md generic repository-topic clone policy
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace boundary
upstream implementation ../../tools/repository/workspace/repository_topic_clone.py lifecycle implementation
downstream implementation ../../tests/agent_tools/test_repository_topic_clone.py validates cleanup and merge gates
@dependency-end
-->

# repository_topic_clone.py

`tools/repository/workspace/repository_topic_clone.py` は、`repository-topic` checkout の
`workspace/<topic>/<repo>` 形 lifecycle を管理する tool です。詳細責務と
clause は
[`documents/rule/repository-topic-clone.md`](../rule/repository-topic-clone.md)
を参照します。

## 基本操作

```bash
python3 tools/repository/workspace/repository_topic_clone.py prepare \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  --owner-evidence <evidence-file> \
  [--allowed-path <relative-path>]...

python3 tools/repository/workspace/repository_topic_clone.py merge-main \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  --owner-evidence <evidence-file>

python3 tools/repository/workspace/repository_topic_clone.py cleanup \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  --owner-evidence <evidence-file> \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

`<parent-root>` は [事前条件](../rule/repository-topic-clone.md#事前条件) で照合する Git toplevel です。
`--checkout-mode` の選択は [Checkout mode](../rule/repository-topic-clone.md#checkout-mode) に従います。
container 側に checkout-mode の別 flag はなく、exact target metadata から自動判定します。
write-capable handoff の各 allowed path は repeated `--allowed-path <relative-path>` で渡します。
exact identity の既存 checkout では、current owner evidence と明示 scope に応じて task marker、reserved packet の
Git common-directory `info/exclude` entry、および ignored writer-target packet のみを更新できます。
linked worktree ではその ignore entry は共有されますが、writer packet は各 worktree に属します。
これは source や Git index を変更せず、dirty checkout を clean 扱い
しません。merge / cleanup の clean-state 条件も変更しません。dirty 状態を保った場合は prepare の出力に
`REQUEST_CHECKOUT_STATUS=dirty-preserved` を含めます。

作成・再利用・writer packet・merge の authority は
[clone ライフサイクル](../rule/repository-topic-clone.md#clone-ライフサイクル)、
復元可能性・marker・任意 publication evidence・削除可否は
[クリーンアップ](../rule/repository-topic-clone.md#クリーンアップ) を確認してから操作します。
`cleanup --apply` の前に task owner が exact path の利用終了と、必要な ignored / untracked / local-only
submodule・annex content を削除対象外へ保存したことを確認します。CLI の clean-status proof は ignored content や
submodule Git metadata/object の再取得可能性を示しません。linked cleanup は proof preflight 後に exact worktree path
を `git worktree remove --force` で一様に回収し、request の local topic branch は保持します。この command に
branch deletion authority を追加せず、branch 操作は既存 owner の別 operation として扱います。成功時は linked
path が消え、`git worktree list` に残っていないことを確認します。
`merge-main` の成功結果は ancestor proof を返します。
adapter の `status` と `projected_clone_path` は directory を作らない read-only projection です。

## 競合の再開

再開・commit の条件は [規約の競合の再開](../rule/repository-topic-clone.md#競合の再開) を参照します。
`merge-main` が競合した場合、native Git の merge state と index stages をその checkout に
残して停止します。integration executor は実際の unmerged paths を確認して source owner と
競合をレビュー・解消します。`finalize-merge` は unresolved index なら native
`git write-tree` が失敗するため commit せず、解決済み index tree と `MERGE_HEAD` に基づく
commit parents を read back します。

```bash
python3 tools/repository/workspace/repository_topic_clone.py finalize-merge \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --owner-evidence <evidence-file> \
  --checkout-mode <linked-worktree|independent-clone>

# `resume-merge` is an alias for `finalize-merge`.
```

`finalize-merge` は native Git index の未解決 entry を拒否し、resolved index tree と
`MERGE_HEAD` を親とする commit を確認します。必要な競合判断は integration owner が実際の
競合をレビューして行い、独自planや別checkerは要求しません。
