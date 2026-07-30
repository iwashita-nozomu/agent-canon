# dependency-module-change

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for dependency module changes.
upstream design ../canonical/skills.md shared skill canon registry
upstream design ../../documents/rule/dependency-module-changes.md detailed dependency module policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace and VS Code workspace boundary
upstream design ../../documents/design/request-intent-and-update-relation.md immediate dependency-clone cleanup projection
downstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle tool
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

依存 module の source 変更、topic branch clone、remote 再構成可能性に基づく
cleanup を同じ責務境界で扱います。

### Compact integration cleanup projection

`../../documents/design/request-intent-and-update-relation.md` の `LIFE-01` は merge/readback
evidence を受けて、この owner の既存 `dependency_module_change.py cleanup --apply` を
dispatch-ready state へ進めます。completion evidence は same-command authority、
reconstructibility readback、および `CLEANUP` receipt です。

## 使う route

詳細な source-clone 判断と AgentCanon parent state decision table は
[`documents/rule/dependency-module-changes.md`](../../documents/rule/dependency-module-changes.md) を唯一の正本として読みます。
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

PR merge/readback 後に topic branch が削除され、clone に local-only commit が
残る場合は、cleanup に `--integrated-commit <full-oid>` として統合 commit の
evidence を渡します。省略時の canonical `origin/main` discovery を含む
equivalence gate と hold 条件は、詳細 policy owner の cleanup gate に従います。
computed clone path、manifest / `origin` URL、clean / untracked-zero state、tree の
inclusion / deletion が証明されていれば、`agent-canon.topic.role` / `topic` の stale または
missing membership marker は旧 evidence として `marker-readback=membership-mismatch` に
明示されるだけで cleanup を阻害しません。owner evidence、placement、module、URL、branch
の不一致は hold します。workspace clone を削除した後、managed child 以外の成果物が無い
topic root は同じ `CLEANUP` receipt で除去されます。再 clone / `prepare` はこの route に
追加しません。

独立した replaceable responsibility を parallel に実行する場合は、vendor の clean
状態を理由に停止せず、親の DAG packet が disjoint write scope、依存/merge order、
validation、reviewer ownership を固定した後で、次の typed route を使います。

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> prepare \
  --placement workspace --topic <topic> --module <path> --branch <branch> \
  --owner-evidence <file>
```

この route は `workspace/<topic-slug>/<module-basename>` の computed clone だけを
fresh create し、親 cloneや代替 pathを作りません。local/remote に requested branch が
存在する場合は拒否します。既存 remote branch の継続は
`--placement workspace-continuation` という別の non-fresh route で明示します。新規 branch は最新
`origin/main` から作られ、`SOURCE_REMOTE`、`SOURCE_BASE_REF`、`SOURCE_BASE_SHA`、
`SOURCE_OWNER_EVIDENCE_SHA256`、`SOURCE_BRANCH`、`SOURCE_HEAD_SHA` を source identity
として返します。相対 `.gitmodules` URL は親 origin identity に対して解決されます。
細粒度の fresh agent や責務単位の過剰分割には使わず、親は ready な独立 stream を
全て launch し、descendant を monitor し、互換な worker context を再利用します。

AgentCanon update はこの一般 route の具体例です。

parent pin/root projection、clean named topic の source owner、requested topic
identity、dirty fallback の typed next action は、同規約の判定表に従います。
`main` は topic 作成の起点であり source owner ではありません。runtime shim や
workflow は `cmd_latest` の更新対象 branch を topic slug に使いません。
