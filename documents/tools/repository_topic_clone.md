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

作成・再利用・writer packet・merge の authority は
[clone ライフサイクル](../rule/repository-topic-clone.md#clone-ライフサイクル)、
復元可能性・marker・任意 publication evidence・削除可否は
[クリーンアップ](../rule/repository-topic-clone.md#クリーンアップ) を確認してから操作します。
`merge-main` の成功結果は ancestor proof を返します。
adapter の `status` と `projected_clone_path` は directory を作らない read-only projection です。

## 競合の再開

再開・commit の条件は [規約の競合の再開](../rule/repository-topic-clone.md#競合の再開) を参照します。
以下は inventory の場所、plan の入力、診断と再開のコマンドです。

`merge-main` が競合した場合は、解消や片側 checkout を実行せず、prepared checkout 内の
`.agent-canon/conflict-preservation.json` に base/ours/theirs の immutable blob
reference、staged/unmerged state、各 hunk、unaffected user/unknown content を保存して
停止します。integration executor は disposition、owner、cause、expected mechanism、exact
edit delta、rationale を含む plan を作り、次の checker で readback を確認します。

```bash
python3 tools/repository/git/conflict_preservation.py capture \
  --repo-root <clone> --base <merge-base> --ours <head> --theirs <origin-main> \
  --output <clone>/.agent-canon/conflict-preservation.json
python3 tools/repository/git/conflict_preservation.py validate \
  --inventory <clone>/.agent-canon/conflict-preservation.json \
  --plan <preservation-plan.json> --repo-root <clone>
python3 tools/repository/git/conflict_preservation.py validate-rework \
  --packet <rework-preservation.json>

python3 tools/repository/workspace/repository_topic_clone.py finalize-merge \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --owner-evidence <evidence-file> \
  [--inventory <inventory.json> --plan <preservation-plan.json>]

# `resume-merge` is an alias for `finalize-merge`.
```

`keep`、`replace`、`manual` のいずれも path ごとの根拠が必要です。whole-file checkout、
reset、reclone、overwrite、regeneration は inventory と reconstruction map がなければ
拒否され、clean な `conflict_paths=empty` だけでは成功になりません。

保持条件は plan の各 path にある `unaffected_content` への明示的な指定だけです。
ただし、過去の stage に gitlink (`160000`) があり、解消後も gitlink が残る場合は、
`expected_gitlink` による mode/OID の readback を必須とします。`unaffected_content: []` は
解消後の index にその path が存在しない実際の削除（または absent stage）に限って保持条件を
空にできます。通常ファイル・gitlink の削除は妨げませんが、削除済みであることは解消後の
Git index/tree の差分で確認します。承認済み削除は既存の `manual` disposition、`rationale`、
`expected_edit_delta` に記録します。新しい delete disposition、absence schema、削除専用の
判定は追加しません。

保持を明示した `expected_blob`、`hunk_identity`、`expected_gitlink` の消失・不一致は引き続き
拒否します。plan の identity と inventory の path coverage、未解決 index の検出も維持します。
この意味は単独の `validate` と、それを呼ぶ `finalize-merge` / `resume-merge` で共通です。
