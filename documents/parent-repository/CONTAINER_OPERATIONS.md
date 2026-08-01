<!--
@dependency-start
contract reference
responsibility Defines parent-repository container operations for the mounted zsh environment contract.
upstream design ../design/devcontainer/parent-devcontainer-policy.md parent devcontainer ownership and startup boundary
upstream design ../structure/repo-structure-contract.toml expected parent paths
downstream implementation ../../.devcontainer/generate-runtime-compose.sh shared Compose generator
downstream implementation ../../tools/ci/container_config.py static container contract validation
downstream implementation ../../tools/agent_tools/parent_repo_readiness.py parent readiness validation
@dependency-end
-->

# 親レポの container 操作

この文書は、AgentCanon を `vendor/agent-canon/` に pin する親レポの
container / devcontainer 操作を定義します。親固有の image は親が所有し、
AgentCanon は mounted developer/agent tool と共有 runtime の source を所有します。

## 所有境界

- 親の `docker/Dockerfile`、runtime pack、workspace Python dependency は親の
  product image contract です。
- `.devcontainer/parent-environment.sh` は親環境の値を定義する唯一の source です。
  値が不要な初期状態では空の regular file を置きます。
- `.devcontainer/parent-environment.toml` は `variables` 配列だけを持ち、shell
  export 名の ordered manifest になります。
- `vendor/agent-canon/.devcontainer/dependencies.toml` は AgentCanon が必要とする
  mounted tool を独立して宣言します。AgentCanon の pinned PyYAML record は、親が
  宣言する PyYAML の ownership を置き換えません。

親の `.devcontainer/` は regular directory のまま保持します。shared
`devcontainer.json` だけを symlink し、shared script のコピーや wrapper は作りません。
生成 Compose と dependency receipt は親の実行状態であり、追跡対象にしません。

## zsh startup の入力

親環境を有効にする Compose は次の read-only bind mount を提供します。

```text
.devcontainer/parent-environment.sh -> /etc/project-template/parent-environment.sh
host ~/.zshrc                         -> /etc/project-template/zsh/.zshrc
```

host `~/.zshrc` は明示的な入力 premise です。generator はその exact path が
regular file であることを確認し、欠落、directory、symlink の場合は失敗します。
別の host path を探索したり、空の zshrc を生成したりしません。

後続の親 image は image-owned `/etc/project-template/zsh/.zshenv` から mounted
`/etc/project-template/parent-environment.sh` を source します。これにより zsh
process boundary と descendants が同じ parent variables を受け取ります。
generator は shell script を実行して値を抽出せず、Compose に parent variable の値を
複製しません。

## pack と Compose

generator は既存の `pack.runtime.shell` を interactive process として使います。
親の default pack は `/bin/zsh` を選び、bash を明示した pack と smoke shell は
`/bin/bash` を使います。別の shell 設定機構は追加しません。

Compose がこの境界で直接所有する environment は次の三つです。

- `HOME`: mapped UID/GID で作成された tmpfs（または同等の直接機構）を zsh startup
  前に提供します。
- `ZDOTDIR`: image-owned zsh startup directory を指します。
- `SHELL`: pack の `runtime.shell` と一致します。

親の `.devcontainer/parent-environment.toml` が構造上必要なことは、値や container
behavior の十分条件ではありません。最終的な親側検証は、validator、readiness、
runtime pack、image startup の各 owner が担当します。

## lifecycle と validation

shared post-create は fixed bootstrap、親 manifest と AgentCanon manifest の merge、
full plan validation、derived execution、親 Python installer、AgentCanon build/cache/
projection の順に進み、最後に親の `post-create-parent.sh` を呼びます。manifest の
validation が pass する前に install や build を開始しません。

source と親の pin を変更する順序、root projection、regular/symlink surface は
[`../design/devcontainer/parent-devcontainer-policy.md`](../design/devcontainer/parent-devcontainer-policy.md)
と shared surface manifest が所有します。親側では次を targeted readback として使います。

```bash
python3 vendor/agent-canon/tools/agent_tools/parent_repo_readiness.py \
  --root <parent-root>
python3 vendor/agent-canon/tools/ci/container_config.py --root <parent-root>
```

これらの構造チェックは必要条件を検査します。ファイルの存在だけで parent
environment の値、image-owned zsh startup、または runtime behavior の十分条件を
主張しません。
