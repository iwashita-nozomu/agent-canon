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
  --expected-clone <absolute-clone> \
  --candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>] [--apply]
```

host は `<parent-root>/workspace/<topic>/<repo>` を想定し、path alias は持ちません。
owner evidence と computed identity が一致する canonical `prepare` / `merge-main` は
operation-level の追加承認なしで repo-local workspace を管理します。reuse は `prepare`
に含まれます。
`prepare` は既存 clone を marker/evidence/branch/url/upstream で検証し、exact branch を
再利用します。不一致は state-preserving typed collision です。`merge-main` は
`origin/main` を通常 merge し、ancestor proof を返します。`cleanup` は canonical
candidate CAS、PR lifecycle、owner evidence を必須とし、integration 後は publication
transition も検証します。pass 時だけ `CleanupProof` を返し、unknown sibling や dirty
collision は保持します。
