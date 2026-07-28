# dependency-module-change

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for dependency module changes.
upstream design ../canonical/skills.md shared skill canon registry
upstream design ../../documents/rule/dependency-module-changes.md detailed dependency module policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace and VS Code workspace boundary
downstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle tool
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

依存 module の source 変更、topic branch clone、remote 再構成可能性に基づく
cleanup を同じ責務境界で扱います。

## 使う route

詳細な source-clone 判断は [`documents/rule/dependency-module-changes.md`](../../documents/rule/dependency-module-changes.md) を読みます。
topic workspace の filesystem / lifecycle、devcontainer mount、VS Code workspace 運用の禁止、
`.vscode/` 共有面の境界は [`documents/contracts/github-first-module-and-devcontainer-policy.md`](../../documents/contracts/github-first-module-and-devcontainer-policy.md)
だけを正本として参照します。`.gitmodules` の identity、`vendor/<module>` の clean
pin/runtime projection、`workspace/<topic-slug>/<module-basename>` source clone、
results owner surface はそれぞれの owner に分けます。

`prepare --topic <topic> --module <path> --branch <task-branch>
--owner-evidence <file> [--parent-branch <pin-branch>]` は owner evidence がある source-edit のときだけ使い、pin-only・
update-only・read-only では clone を作りません。返された `PARENT_ROOT`、
`SOURCE_CLONE`、`CONTINUE_PATH` は正本契約の filesystem / lifecycle 作業領域で
使います。cleanup は dry-run を経て remote に全 state がある場合
だけ apply します。

AgentCanon update はこの一般 route の具体例です。parent mode の vendor
checkout を source branch として保存・継続・fallback する経路は使わず、
独立 source clone route へ戻します。
