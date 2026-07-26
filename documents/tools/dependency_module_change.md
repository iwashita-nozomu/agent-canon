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
`.gitmodules` を構造的に読み、topic workspace と branch-specific source clone を管理する
workflow helper です。詳細な責務・cleanup gate・禁止事項は
[`documents/rule/dependency-module-changes.md`](../rule/dependency-module-changes.md)
を参照します。

```bash
python3 tools/agent_tools/dependency_module_change.py --root <repo> status --topic <topic>
python3 tools/agent_tools/dependency_module_change.py --root <repo> prepare \
  --topic <topic> --module vendor/agent-canon --branch <task-branch> \
  --owner-evidence <evidence-file> [--parent-branch <pin-branch>]
python3 tools/agent_tools/dependency_module_change.py --root <topic-parent> workspace \
  --topic <topic>
python3 tools/agent_tools/dependency_module_change.py --root <topic-parent> cleanup \
  --topic <topic> --module vendor/agent-canon --expected-clone <absolute-clone> \
  [--apply]
```

host は `workspace-<topic-slug>/<parent>` とその同列 module cloneだけを保持します。
clone名は `<module-basename>` でbranchはGit内部marker/actual branch identityです。
`.gitmodules` の `branch` は optional な clone base であり、task branch とは別です。
remote に task branch があれば tracking checkout、なければ clone base から作成します。
prepare 完了時には workspace projection も生成します。
container はtopic workspace root全体を `/workspace` に一度だけ mountし、同じworkspace JSONの相対 pathを
使います。`AGENT_CANON_WORKSPACE_ROOT` は container では `/workspace` 固定です。
`cleanup --apply` は、同じ command segment の authority/reason 環境変数と
remote 再構成可能性を要求します。clone mapping JSON は生成しません。
