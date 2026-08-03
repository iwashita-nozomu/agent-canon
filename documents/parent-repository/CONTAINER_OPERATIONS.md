<!--
@dependency-start
contract reference
responsibility Defines parent-repository container operations for the reconstructible non-root devcontainer contract.
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
- `.devcontainer/parent-environment.sh` と
  `.devcontainer/parent-environment.toml` は legacy evidence として残っていても
  よいが、devcontainer create、shell startup、runtime/tool availabilityの入力に
  しません。parent runtime値は Docker `ENV`、devcontainer `containerEnv`、明示
  bootstrap、または workspace sourceで再構成します。
- `vendor/agent-canon/.devcontainer/dependencies.toml` は AgentCanon が必要とする
  mounted tool を独立して宣言します。AgentCanon の pinned PyYAML record は、親が
  宣言する PyYAML の ownership を置き換えません。

親の `.devcontainer/` は regular directory のまま保持します。shared
`devcontainer.json` だけを symlink し、shared script のコピーや wrapper は作りません。
生成 Compose と dependency receipt は親の実行状態であり、追跡対象にしません。

## host mount inventory と zsh startup

default Composeのrequired host bindはworkspace repository topic-rootから`/workspace`
への一つだけです。GPU device/driver runtime passthroughはhost GPUが利用可能な
場合のruntime capabilityで、imageへdriverを入れません。

host `${HOME}/.zshrc` は regular file の場合だけ `/home/project/.zshrc` へread-only
projectionする唯一のoptional user-customizationです。欠落・directory・symlinkの場合
はmountを省略し、image-owned empty/default `/home/project/.zshrc`で同一機能を成立させ
ます。host `~/.codex`、parent-environment、個別credential/config、SSH agent、previous
container state、`/mnt/git`、Docker socketはdefault create/tool availabilityの入力
ではありません。

`AGENT_CANON_OPTIONAL_MOUNTS` の明示profileだけが `host-git`、`host-secrets`,
`host-credentials`、`ssh-agent`、`docker-host`、`shared-runtime` を有効化できます。
Docker-in-Docker/host daemonは`docker-host` profileに限定します。zsh startupは
`.zshenv`、`ZDOTDIR`、parent-environment sourceに依存せず、Docker `ENV`、
devcontainer `containerEnv`、明示bootstrapからruntime値を受け取ります。

## pack と Compose

generator は既存の `pack.runtime.shell` を interactive process として使います。
親の default pack は `/bin/zsh` を選び、bash を明示した pack と smoke shell は
`/bin/bash` を使います。別の shell 設定機構は追加しません。
standalone AgentCanon source layout では pack-derived command だけを生成し、host
`~/.zshrc`、parent environment mount、`HOME`、tmpfs は要求しません。

Compose がこの境界で直接所有する environment は次の四つです。

- `HOME`: dedicated non-root userの `/home/project` を指します。
- `SHELL`: pack の `runtime.shell` と一致します。
- `AGENT_CANON_CONTAINER_USER`: `project` と一致し、post-create/attachがruntime
  user、HOME、ownershipをread backします。

parent environment pair の両方不在、または両方が file 実体へ解決できることは、値や
container behavior の十分条件ではありません。最終的な親側検証は、validator、
readiness、runtime pack、image startup の各 owner が担当します。

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
