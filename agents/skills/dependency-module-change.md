# dependency-module-change

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for dependency module changes.
upstream design ../canonical/skills.md shared skill canon registry
upstream design ../../documents/rule/dependency-module-changes.md detailed dependency module policy
downstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle tool
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

依存 module の source 変更、topic branch clone、remote 再構成可能性に基づく
cleanup を同じ責務境界で扱います。

## 使う route

詳細な判断は [`documents/rule/dependency-module-changes.md`](../../documents/rule/dependency-module-changes.md) だけを読みます。`.gitmodules` の identity、`vendor/<module>` の clean pin/runtime projection、`workspace-<topic-slug>/<module-basename>` source clone、results owner surface の順に責務を分けます。

`prepare --topic <topic> --module <path> --branch <task-branch>
--owner-evidence <file> [--parent-branch <pin-branch>]` は owner evidence がある source-edit のときだけ使い、pin-only・
update-only・read-only では clone を作りません。返された `PARENT_ROOT`、
`SOURCE_CLONE`、`CONTINUE_PATH` は VS Code の標準 multi-root 操作（`Add Folder
to Workspace` または `code --add <parent-clone> <dependency-clone>`）に渡します。
必要なら利用者が標準の `Save Workspace As...` を使えますが、保存場所と JSON は
AgentCanon の契約外です。cleanup は dry-run を経て remote に全 state がある場合
だけ apply します。

AgentCanon update はこの一般 route の具体例です。parent mode の vendor
checkout を source branch として保存・継続・fallback する経路は使わず、
独立 source clone route へ戻します。
