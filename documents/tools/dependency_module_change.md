<!--
@dependency-start
contract reference
responsibility Documents the dependency module source-clone lifecycle command.
upstream design ../rule/dependency-module-changes.md generic dependency module policy
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
python3 tools/agent_tools/dependency_module_change.py --root <topic-parent> cleanup \
  --topic <topic> --module vendor/agent-canon --expected-clone <absolute-clone> \
  [--apply]
```

host は `workspace-<topic-slug>/<parent>` とその同列 module cloneだけを保持します。
clone名は `<module-basename>` でbranchはGit内部marker/actual branch identityです。
`.gitmodules` の `branch` は optional な clone base であり、task branch とは別です。
remote に task branch があれば tracking checkout、なければ clone base から作成します。
prepare は `PARENT_ROOT`、`SOURCE_CLONE`、`CONTINUE_PATH` を返します。これらの
clone path を VS Code の標準 multi-root 操作（`Add Folder to Workspace` または
`code --add <parent-clone> <dependency-clone>`）に渡します。利用者は必要なら
標準の `Save Workspace As...` を使えますが、保存場所と JSON は AgentCanon の
契約外です。container は topic workspace root 全体を `/workspace` に一度だけ mount
し、`AGENT_CANON_WORKSPACE_ROOT` は container では `/workspace` 固定です。
`cleanup --apply` は、同じ command segment の authority/reason 環境変数と
remote 再構成可能性を要求します。
