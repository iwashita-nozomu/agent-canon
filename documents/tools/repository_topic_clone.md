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

```bash
python3 tools/repository/workspace/repository_topic_clone.py prepare \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --checkout-mode <linked-worktree|independent-clone> \
  --owner-evidence <evidence-file>

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

host は `<parent-root>/workspace/<topic>/<repo>` を想定し、path alias は持ちません。parent または
同一 repository の branch は `linked-worktree`、dependency repository は `independent-clone` を
選びます。container 側に checkout-mode の別 flag はなく、exact target metadata から自動判定します。
owner evidence と computed identity が一致する canonical `prepare` / `merge-main` は
operation-level の追加承認なしで repo-local workspace を管理します。reuse は `prepare`
に含まれます。
`<parent-root>` は selected repository の Git toplevel と一致し、root の regular/tracked
`.gitignore` が `workspace/` を ignore する必要があります。`prepare` / `merge-main` は
workspace/topic directory の作成前に symlink component、toplevel、tracked ignore、
`workspace/.agent-canon-workspace-probe` の ignore source を検証し、global/info exclude
だけで成立する root や nested/non-repository root を typed error として保持します。
`prepare` は既存 checkout を marker/evidence/branch/url/upstream で検証し、exact branch を
再利用します。不一致は state-preserving typed collision です。`merge-main` は
`origin/main` を通常 merge し、ancestor proof を返します。`cleanup` は computed checkout の
identity、owner evidence、clean branch を検証します。linked-worktree は保持された local branch
と共有 Git common objects の readback で復元可能性を確認し、remote branch を要求しません。
`independent-clone` は fetch した `origin/<branch>` の commit/tree と local head/tree の一致を
検証する external recoverability proof を要求します。candidate CAS、PR lifecycle、publication
transition は任意の追加 evidence であり、publication readback を渡した merged state では
strict publication readback、merge tree、`origin/main` containment を追加確認します。pass 時だけ
`CleanupProof` を返し、unknown sibling や dirty collision は保持します。
`cleanup` は exact Git toplevel を検証してから proof preflight を実行し、root ignore の
後続 driftだけでは既存 checkout の proof-gated removalを停止しません。adapter の `status`
と `projected_clone_path` は directory を作らない read-only projection です。

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
inventory に path が存在することや、過去の stage が gitlink (`160000`) であることから、
存在や型の保持を自動的に要求しません。`unaffected_content: []` は保持条件が空であることを
表し、通常ファイル・gitlink の削除も妨げません。ただし、これは削除済みであることの証明では
ありません。承認済み削除は既存の `manual` disposition、`rationale`、`expected_edit_delta`
に記録し、解消後の Git index/tree の差分で確認します。新しい delete disposition、absence
schema、削除専用の判定は追加しません。

保持を明示した `expected_blob`、`hunk_identity`、`expected_gitlink` の消失・不一致は引き続き
拒否します。plan の identity と inventory の path coverage、未解決 index の検出も維持します。
この意味は単独の `validate` と、それを呼ぶ `finalize-merge` / `resume-merge` で共通です。
