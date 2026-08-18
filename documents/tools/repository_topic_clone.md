<!--
@dependency-start
contract reference
responsibility Documents the repository-topic clone lifecycle command.
upstream design ../rule/repository-topic-clone.md generic repository-topic clone policy
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace boundary
upstream implementation ../../tools/agent_tools/repository_topic_clone.py lifecycle implementation
downstream implementation ../../tests/agent_tools/test_repository_topic_clone.py validates cleanup and merge gates
@dependency-end
-->

# repository_topic_clone.py

`tools/agent_tools/repository_topic_clone.py` は、`repository-topic` clone の
`workspace/<topic>/<repo>` 形 lifecycle を管理する tool です。詳細責務と
clause は
[`documents/rule/repository-topic-clone.md`](../rule/repository-topic-clone.md)
を参照します。

```bash
python3 tools/agent_tools/repository_topic_clone.py prepare \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --owner-evidence <evidence-file>

python3 tools/agent_tools/repository_topic_clone.py merge-main \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --owner-evidence <evidence-file>

python3 tools/agent_tools/repository_topic_clone.py cleanup \
  --url <remote-url> --repo-name <repo-name> --workspace-root <parent-root> \
  --topic <topic> --branch <task-branch> --owner-evidence <evidence-file> \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

host は `<parent-root>/workspace/<topic>/<repo>` を想定し、path alias は持ちません。
owner evidence と computed identity が一致する canonical `prepare` / `merge-main` は
operation-level の追加承認なしで repo-local workspace を管理します。reuse は `prepare`
に含まれます。
`<parent-root>` は selected repository の Git toplevel と一致し、root の regular/tracked
`.gitignore` が `workspace/` を ignore する必要があります。`prepare` / `merge-main` は
workspace/topic directory の作成前に symlink component、toplevel、tracked ignore、
`workspace/.agent-canon-workspace-probe` の ignore source を検証し、global/info exclude
だけで成立する root や nested/non-repository root を typed error として保持します。
`prepare` は既存 clone を marker/evidence/branch/url/upstream で検証し、exact branch を
再利用します。不一致は state-preserving typed collision です。`merge-main` は
`origin/main` を通常 merge し、ancestor proof を返します。`cleanup` は computed clone の
identity、owner evidence、clean branch、fetch した `origin/<branch>` の commit/tree と local
head/tree の一致を検証します。candidate CAS、PR lifecycle、publication transition は任意の
追加 evidence であり、merged state の場合だけ strict publication readback を要求します。
pass 時だけ `CleanupProof` を返し、unknown sibling や dirty collision は保持します。
`cleanup` は exact Git toplevel を検証してから proof preflight を実行し、root ignore の
後続 driftだけでは既存 clone の proof-gated removalを停止しません。adapter の `status`
と `projected_clone_path` は directory を作らない read-only projection です。
