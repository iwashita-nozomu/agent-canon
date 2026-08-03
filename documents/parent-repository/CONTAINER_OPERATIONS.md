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
- `.devcontainer/parent-environment.sh` と
  `.devcontainer/parent-environment.toml` は optional pair です。両方がない状態は
  parent environment 無効として成立します。
- parent environment を有効にする場合、shell file は親環境の値を定義する唯一の
  source、TOML は `variables` 配列だけを持つ shell export 名の ordered manifest
  になります。両 path は regular file または regular file へ解決できる Symlink
  とし、片方だけの宣言と broken / non-file Symlink は失敗です。
- `vendor/agent-canon/.devcontainer/dependencies.toml` は AgentCanon が必要とする
  mounted tool を独立して宣言します。AgentCanon の pinned PyYAML record は、親が
  宣言する PyYAML の ownership を置き換えません。

親の `.devcontainer/` は regular directory のまま保持します。shared
`devcontainer.json` だけを symlink し、shared script のコピーや wrapper は作りません。
生成 Compose と dependency receipt は親の実行状態であり、追跡対象にしません。

## zsh startup の入力

optional pair で親環境を有効にする Compose は次の read-only bind mount を提供します。

```text
.devcontainer/parent-environment.sh -> /etc/project-template/parent-environment.sh
host ~/.zshrc                         -> /home/project/.zshrc (when regular file exists)
```

parent environment の両 path がない場合は一つ目の mount と source を生成しません。
宣言された shell path は regular file 自身でも、regular file へ解決できる Symlink
でも同じ親所有 source として扱います。

host `${HOME}/.zshrc` は明示的な optional mount source expression です。validator は
生成Composeにmountがある場合のbind type、source expression、non-root target、
read-onlyを静的に検証します。実行時には展開後のexact pathがregular fileの場合だけ
mountし、欠落・directory・symlinkではmountを省略します。fresh clone / CI validation
は現在のrunner host fileをprobeしません。別のhost pathを探索したり、空のzshrcを生成
したりしません。

parent environment が有効な場合、後続の親 image は image-owned
`/etc/project-template/zsh/.zshenv` から mounted
`/etc/project-template/parent-environment.sh` を source します。これにより zsh
process boundary と descendants が同じ parent variables を受け取ります。
generator は shell script を実行して値を抽出せず、Compose に parent variable の値を
複製しません。

## pack と Compose

generator は既存の `pack.runtime.shell` を interactive process として使います。
親の default pack は `/bin/zsh` を選び、bash を明示した pack と smoke shell は
`/bin/bash` を使います。別の shell 設定機構は追加しません。
standalone AgentCanon source layout では pack-derived command だけを生成し、host
`~/.zshrc`、parent environment mount、`HOME`、`ZDOTDIR`、tmpfs は要求しません。

Compose がこの境界で直接所有する environment は次の四つです。

- `HOME`: dedicated non-root userの `/home/project` を指します。
- `ZDOTDIR`: `/home/project` を指し、image-owned `.zshenv` はoptional host `.zshrc` の
  有無にかかわらず parent environment をsourceします。
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
