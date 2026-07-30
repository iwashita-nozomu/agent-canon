<!--
@dependency-start
contract reference
responsibility Documents the dependency module source-clone lifecycle command.
upstream design ../rule/dependency-module-changes.md generic dependency module policy
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace and VS Code workspace boundary
upstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle implementation
downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates command behavior
@dependency-end
-->

# dependency_module_change.py

`tools/agent_tools/dependency_module_change.py` は、親 repository の
`.gitmodules` を構造的に読み、topic root と branch-specific source clone を管理する
workflow helper です。詳細な責務・cleanup gate・禁止事項は
[`documents/rule/dependency-module-changes.md`](../rule/dependency-module-changes.md)
を参照します。

```bash
python3 tools/agent_tools/dependency_module_change.py --root <repo> status --topic <topic>
python3 tools/agent_tools/dependency_module_change.py --root <repo> prepare \
  --topic <topic> --module vendor/agent-canon --branch <task-branch> \
  --owner-evidence <evidence-file> [--parent-branch <pin-branch>]
python3 tools/agent_tools/dependency_module_change.py --root <repo> prepare \
  --placement workspace --topic <topic> --module vendor/agent-canon \
  --branch <task-branch> --owner-evidence <evidence-file>
python3 tools/agent_tools/dependency_module_change.py --root <topic-parent> cleanup \
  --topic <topic> --module vendor/agent-canon --expected-clone <absolute-clone> \
  [--integrated-commit <full-oid>] [--apply]
python3 tools/agent_tools/dependency_module_change.py --root <repo> cleanup \
  --placement workspace --topic <topic> --module vendor/agent-canon \
  --expected-clone <absolute-clone> --owner-evidence-sha256 <sha256> \
  [--integrated-commit <full-oid>] [--apply]
```

host は `<parent-repo-root>/workspace/<topic-slug>/<parent>` とその同列 module cloneだけを保持します。
clone名は `<module-basename>` でbranchはGit内部marker/actual branch identityです。
`.gitmodules` の `branch` は optional な clone base であり、task branch とは別です。
remote に task branch があれば tracking checkout、なければ clone base から作成します。
prepare は `PARENT_ROOT`、`SOURCE_CLONE`、`CONTINUE_PATH` を返します。topic workspace
の filesystem / lifecycle、devcontainer mount、VS Code workspace 運用の禁止、
`.vscode/` 共有面の境界は [`github-first-module-and-devcontainer-policy.md`](../contracts/github-first-module-and-devcontainer-policy.md)
だけを参照します。
`cleanup --apply` は、同じ command segment の authority/reason 環境変数と
remote 再構成可能性を要求します。
`--placement workspace` は独立 parallel stream 用の typed fresh route です。親 cloneを
作らず、`<repo>/workspace/<topic-slug>/<module-basename>` だけを computed source clone
として作成し、local/remote に既存の task branch があれば拒否して最新 `origin/main`
から task branch を作成します。既存 remote branch の継続は
`--placement workspace-continuation` で明示します。出力の `SOURCE_REMOTE`、
`SOURCE_BASE_REF`、`SOURCE_BASE_SHA`、`SOURCE_OWNER_EVIDENCE_SHA256`、
`SOURCE_BRANCH`、`SOURCE_HEAD_SHA` が source identity です。workspace cleanup は
`--owner-evidence-sha256` の exact match と marker validation を要求します。
topic branch deletion 後に local-only commit が残る場合の `--integrated-commit` は
PR merge/readback の full OID を渡す typed integration evidence です。省略時の
canonical discovery と Git equivalence/hold semantics は dependency-module policy
owner を参照します。
