<!--
@dependency-start
contract reference
responsibility Defines parent-repository container operations for the reconstructible non-root devcontainer contract.
upstream design ../design/devcontainer/parent-devcontainer-policy.md parent devcontainer ownership and startup boundary
upstream design ../structure/repo-structure-contract.toml expected parent paths
downstream implementation ../../.devcontainer/generate-runtime-compose.sh parent-owned Compose generator; standalone source entrypoints are invoked through the source-root resolver
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

親の `.devcontainer/` は親が所有する regular directory のまま保持します。
`devcontainer.json` を含む regular files は親の environment contract で管理し、
AgentCanon source からの symlink・コピー・削除は行いません。生成 Compose と
dependency receipt は親の実行状態であり、追跡対象にしません。

## host mount inventory と zsh startup

default Composeのrequired host bindはworkspace repository topic-rootから`/workspace`
への一つだけです。GPU device/driver runtime passthroughはhost GPUが利用可能な
場合のruntime capabilityで、imageへdriverを入れません。

host `${HOME}/.zshrc` と `${HOME}/.zsh` は optional user-customizationです。
`host-zshrc` profileが明示された場合、regular fileまたはregular fileへ解決するsymlink
は `realpath -e` のcanonical absolute sourceから `/home/project/.zshrc` へread-only
projectionし、regular directoryへ解決する `${HOME}/.zsh` も `/home/project/.zsh` へ
read-only projectionします。欠落・broken symlink・型違いの場合はmountを省略し、
image-owned empty/default startupで同一機能を成立させます。host `~/.codex`、
parent-environment、個別credential/config、SSH agent、previous container state、
`/mnt/git`、Docker socketはdefault create/tool availabilityの入力ではありません。

`AGENT_CANON_OPTIONAL_MOUNTS` の明示profileだけが `host-zshrc`、`host-git`、`host-secrets`,
`host-credentials`、`ssh-agent`、`docker-host`、`shared-runtime`、
`linked-data-roots` を有効化できます。`shared-runtime` は `gpu-admission` profile に、
Docker-in-Docker/host daemonは`docker-host` profileに限定します。zsh startupは
`.zshenv`、`ZDOTDIR`、parent-environment sourceに依存せず、Docker `ENV`、
devcontainer `containerEnv`、明示bootstrapからruntime値を受け取ります。

pack は `[runtime] optional_mount_profiles` の順序を選択 profile として宣言でき、環境
の comma list と union した canonical order（pack順、環境-only順、cross-sourceは
first-wins）を Compose に read backします。`linked-data-roots` は pack の
`linked_data_roots = [{link = "...", target = "/mnt/l/..."}]` と相互必須で、resolved
directoryが declared target に exact 一致する場合だけ `source == target`、
`read_only: false` の structured bindを生成します。raw `runtime.mounts` は引き続き
拒否し、短い Docker bind 表記を安全に保つため target の `:` と `,` も拒否します。
host probe は validator の入力にしません。

直接 pack runner (`tools/ci/run_container_pack.py`) は pack の
`linked-data-roots` と明示した `docker-host` profile だけをそれぞれの bind contract で
適用します。host zshrc/.zsh やその他の devcontainer-only profile は直接 runner が暗黙に
適用せず、`runtime.mounts` の raw bind は拒否します。`docker-host` は既存の
`/var/run/docker.sock` Unix socketを同じ read-write targetへ bindし、欠落時は fail-closed
です。runner の CLI mount が declared linked target または docker socket target と衝突する
場合も fail-closed とし、profile target の上書きを許しません。

## pack と Compose

generator は既存の `pack.runtime.shell` を interactive process として使います。
親の default pack は `/bin/zsh` を選び、bash を明示した pack と smoke shell は
`/bin/bash` を使います。別の shell 設定機構は追加しません。
standalone AgentCanon source layout でも `host-zshrc` profile は同じ optional host
shell projectionを使えます。profile未選択時は pack-derived command だけを生成し、
host `~/.zshrc`、parent environment mount、`HOME`、tmpfs は要求しません。

Compose がこの境界で直接所有する environment は次の四つです。

- `HOME`: dedicated non-root userの `/home/project` を指します。
- `SHELL`: pack の `runtime.shell` と一致します。
- `AGENT_CANON_CONTAINER_USER`: `project` と一致し、post-create/attachがruntime
  user、HOME、ownershipをread backします。

parent environment pair の両方不在、または両方が file 実体へ解決できることは、値や
container behavior の十分条件ではありません。最終的な親側検証は、validator、
readiness、runtime pack、image startup の各 owner が担当します。

## lifecycle と validation

親の post-create lifecycle は fixed bootstrap、親 manifest と AgentCanon manifest の merge、
full plan validation、derived execution、親 Python installer、AgentCanon build/cache/
projection の順に進み、最後に親の `post-create-parent.sh` を呼びます。manifest の
validation が pass する前に install や build を開始しません。

source と親の pin を変更する順序、active root view、regular/symlink surface は
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
