<!--
@dependency-start
contract design
responsibility 親レポの devcontainer 所有境界と直接参照の契約を定義する。
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership and topology
upstream design ../../runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface manifest
upstream design ../../contracts/github-first-module-and-devcontainer-policy.md devcontainer ownership boundary
downstream implementation ../../../tools/agent_tools/surface_manifest.py materializes and checks shared surface entries
downstream implementation ../../../tools/sync_agent_canon.sh materializes AgentCanon root views
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py checks the minimum parent structure
downstream implementation ../../../tools/ci/container_config.py validates parent environment names without shell execution
downstream implementation ../../../.devcontainer/generate-runtime-compose.sh mounts parent environment sources and host zshrc
downstream design parent-dependency-manifest-followup.md declares the parent manifest, pin, and ordering follow-up
@dependency-end
-->

# 親レポの devcontainer 境界

## 最低限の構造

親レポの `.devcontainer/` は親が所有する実ディレクトリです。最低限、次だけを
固定します。

- `.devcontainer/devcontainer.json` は
  `vendor/agent-canon/.devcontainer/devcontainer.json` への symlink。
- 親固有の処理がある場合は `.devcontainer/post-create-parent.sh` に置く。
- `.devcontainer/parent-environment.sh` は親の環境値を定義する regular file。
  初期状態では空でもよい。
- `.devcontainer/parent-environment.toml` は `variables` 配列だけを持つ regular
  file。配列順が環境 export の順序を定義する。
- AgentCanon の共有スクリプトを親 `.devcontainer/` にコピーしたり、wrapper を
  追加したりしない。

この最低限以外の親レポ固有ディレクトリやファイルを禁止しない。構造検査は
この所有境界と symlink の健全性だけを確認し、親レポの拡張余地を奪わない。

## 親環境の値と名前

`parent-environment.sh` が親環境の値と定義の唯一の source です。validator は
このファイルを shell として実行せず、空行・コメントと `export NAME=value` 形式の
行だけを静的に読みます。`parent-environment.toml` は次の形で ordered variable
names だけを持ちます。

```toml
variables = ["PROJECT_TOKEN", "PROJECT_REGION"]
```

validator は export name と TOML の `variables` を順序付きで完全一致させます。
許可されない shell 行、重複名、未知の TOML key、name の不正、順序差は failure
です。構造検査でファイルが存在しても、値の定義、Compose の意味、image の zsh
startup、host premise の十分条件を証明したことにはなりません。

## 直接参照

symlink 先の `devcontainer.json` は、親レポのルートから AgentCanon の実体を
直接呼び出す。

- bootstrap:
  `vendor/agent-canon/.devcontainer/bootstrap-shared-runtime.sh`
- Compose generator:
  `vendor/agent-canon/.devcontainer/generate-runtime-compose.sh`
- post-create:
  `vendor/agent-canon/.devcontainer/post-create.sh`
- post-attach:
  `vendor/agent-canon/.devcontainer/post-attach.sh`

親環境を使うときは、generator が次を read-only bind mount します。

- `.devcontainer/parent-environment.sh` ->
  `/etc/project-template/parent-environment.sh`
- host の明示的な `~/.zshrc` -> `/etc/project-template/zsh/.zshrc`

host `~/.zshrc` は regular file であることを実行前提とし、欠落・directory・symlink
を別の guessed path で補いません。image-owned
`/etc/project-template/zsh/.zshenv` は後続の親 image 側でこの read-only mounted
parent script を source します。

generator は既存の `pack.runtime.shell` を process boundary として使います。親の
default pack は zsh を選び、明示的な bash pack と smoke shell は bash のままです。
zsh とその descendants は zsh startup を通じて parent variables を受け取ります。
Compose が parent variables の値を再定義することはなく、関連する Compose-owned
environment は `HOME`、`ZDOTDIR`、`SHELL` だけです。mapped UID/GID の `HOME` は
zsh startup より前に generator が用意する tmpfs（または同等の直接機構）です。

Compose の生成先は親レポの `.agent-canon/docker-compose.generated.yml` とする。
`.agent-canon/` は親レポの実行状態用であり、生成 Compose を追跡対象にしない。

## post-create の順序

`postCreateCommand` は AgentCanon の共有 `post-create.sh` を先に呼び、成功した
後に親固有の `post-create-parent.sh` を直接呼ぶ。共有処理が失敗した場合は親固有
処理へ進まない。親固有処理の失敗も devcontainer 作成の失敗として扱う。

shared post-create の内部順序は
fixed bootstrap、親 manifest、vendor manifest、全体 validation、
topological derived execution、親の
docker/install_python_dependencies.sh、AgentCanon build/cache/projection の順です。
この shared command の完了後に、devcontainer.json の直接参照が親の
post-create-parent.sh を最後に実行します。詳細な親側 follow-up は
parent-dependency-manifest-followup.md に従います。

AgentCanon は mounted tool のために独立した pinned PyYAML record を持ちます。
親が `docker/requirements.txt` または親 manifest で PyYAML を宣言している場合も、
その親 ownership は保持します。fixed bootstrap の packaging / tomli 契約はこの
source change で変更せず、親の Python 3.11 移行時の tomli 整理は親側 follow-up
です。依存 manifest の plan validation が pass するまで install は開始しません。

## 禁止する重複

- `.devcontainer` 全体を symlink にする。
- AgentCanon の共有 script を親側へコピーする。
- 共有 script を呼ぶだけの親 wrapper を作る。
- 生成 Compose を `.devcontainer/` と `.agent-canon/` の両方へ作る。
- parent environment の値を Compose に複製したり、別の shell configuration
  mechanism を追加したりする。

AgentCanon の共有実装を変更するときは AgentCanon source clone で変更し、PR を
`main` に統合してから、親レポの submodule pin を更新する。

親側の container 操作と image / mounted-tool の責務は
[`../../parent-repository/CONTAINER_OPERATIONS.md`](../../parent-repository/CONTAINER_OPERATIONS.md)
に集約します。
