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

依存 module の `.gitmodules` identity、gitlink、pin、projection を generic
repository topic clone lifecycle へ接続します。clone path、branch selection、
`origin/main` merge、publication receipt、cleanup authority は
`repository-topic-clone` が所有し、この skill は再定義しません。

## 使う route

generic lifecycle は
[`agents/skills/repository-topic-clone.md`](repository-topic-clone.md) と
[`documents/rule/repository-topic-clone.md`](../../documents/rule/repository-topic-clone.md)
を読みます。依存 module 固有の identity と AgentCanon parent state decision table は
[`documents/rule/dependency-module-changes.md`](../../documents/rule/dependency-module-changes.md) を唯一の正本として読みます。
topic workspace の filesystem / lifecycle、devcontainer mount、VS Code workspace 運用の禁止、
`.vscode/` 共有面の境界は [`documents/contracts/github-first-module-and-devcontainer-policy.md`](../../documents/contracts/github-first-module-and-devcontainer-policy.md)
だけを正本として参照します。`.gitmodules` の identity、`vendor/<module>` の clean
pin/runtime projection、`workspace/<topic-slug>/<module-basename>` source clone、
results owner surface はそれぞれの owner に分けます。

source edit では `.gitmodules` の module URL/name を generic request に写像し、exact
local/remote branch を再利用するか、不在 branch を最新 `origin/main` から作成します。
specialized precondition が成立しない場合は dependency decorator だけを外し、user が
要求した clone/edit/update operation を generic owner へ戻します。manual clone や
operation refusal は代替 route ではありません。

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> prepare \
  --topic <topic> --module <path> --branch <branch> \
  --owner-evidence <file>
```

PR 作成時または merge/readback 後の cleanup は canonical lifecycle artifacts を同じ
call に渡します。dry-run も全 authority を検証し、pass 後だけ `--apply` します。

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> cleanup \
  --topic <topic> --module <path> --branch <branch> \
  --owner-evidence <file> --expected-clone <absolute-clone> \
  --candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>] [--apply]
```

completion evidence は generic prepare/merge receipt、dependency identity readback、
pin/projection validation、canonical publication evidence、および `CleanupProof` です。
