# repository-topic-clone

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for repository-topic clone operations.
upstream design ../canonical/skills.md skill canon registry
upstream design ../internal-routines/design-implementation-correspondence.md design read/fingerprint/handoff route
upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md topic workspace boundary
downstream implementation ../../tools/agent_tools/repository_topic_clone.py lifecycle tool
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

repository-topic clone の lifecycle、normal merge、receipted cleanup を
`workspace/<topic-slug>/<repo-name>` の責務境界で扱います。

## 使用 route

依存 module ではなく repository-topic clone を扱う場合、この skill は
`repository_topic_clone.py` を起点にし、`.gitmodules` の gitlink/pin/projection
判断は `dependency-module-change` へ委譲し重複しません。
scope は structure、dependency、差し替え可能な責務単位から形成し、`.gitignore`、
file size、diff size で owner route を固定しません。

## 使う command

- `python3 tools/agent_tools/repository_topic_clone.py prepare ...`
- `python3 tools/agent_tools/repository_topic_clone.py merge-main ...`
- `python3 tools/agent_tools/repository_topic_clone.py cleanup ...`

`--workspace-root` は既存 topic root を再利用し、指定 topic の
`workspace/<topic-slug>` だけを管理します。exact local/remote branch は同じ prepare で
再利用し、不一致は state-preserving typed collision とします。specialized adapter が
適用外でもこの generic operation は継続します。
