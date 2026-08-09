<!--
@dependency-start
contract reference
responsibility Defines the expected structure and ownership boundaries of a parent repository that vendors AgentCanon.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership and projection policy
upstream design ../structure/repo-structure-contract.toml machine-readable expected path contract
upstream design ../rule/directory-structure.md directory documentation and responsibility rule
upstream implementation ../../tools/agent_tools/parent_repo_readiness.py parent repository structure readiness checker
upstream implementation ../../tools/agent_tools/surface_manifest.py shared surface materialization and check
downstream design ../../README.md AgentCanon source reader route
@dependency-end
-->

# 親レポ構造

この文書は、AgentCanon を `vendor/agent-canon/` に pin する template / 派生
親レポに期待する構造、各 surface の所有者、Symlink と実体 directory の意味を
定義します。AgentCanon 自体の source tree の構造説明ではありません。

## 正本の分担

- この README: 親レポ root の期待構造と、active view / regular / retired
  surface の使い分け。
- `../SHARED_RUNTIME_SURFACES.md`: shared surface の source、projection、更新
  手順の正本。
- `../repo-structure-contract.toml`: checker が読む path と mode の正本。
- 各 directory の `README.md` または owner document: その directory 内の子構造と
  個別責務の正本。この README に子構造の説明を複製しない。
- `CONTAINER_OPERATIONS.md`: 親レポの image、mounted tool、zsh startup、Compose
  environment の操作正本。
- 親レポ root の `documents/README.md`: 親レポ固有文書の索引。AgentCanon の
  shared document は `vendor/agent-canon/documents/` を読む。

## Root の最低限構造

```text
<parent-root>/
├── AGENTS.md -> vendor/agent-canon/ROOT_AGENTS.md
├── README.md                         # parent-owned regular file
├── .codex/
│   └── config.toml -> vendor/agent-canon/.codex/config.toml
├── .devcontainer/                    # parent-owned regular directory
│   ├── parent-environment.sh         # optional pair: value source
│   ├── parent-environment.toml       # optional pair: ordered name manifest
│   └── post-create-parent.sh         # parent-specific source
├── .gitmodules                       # AgentCanon submodule declaration
├── documents/README.md                # parent document index
├── tools/
│   └── agent-canon -> ../vendor/agent-canon/tools
└── vendor/agent-canon/                # AgentCanon submodule pin
```

The active child views `.codex/config.toml` and `tools/agent-canon` shown above are
required when the AgentCanon runtime is installed. Additional children under
`.codex/` and `tools/` are parent-owned optional content. Other allowed extensions
include `.agents/`, `agents/`, `.github/`, `.vscode/`, `docker/`, `experiments/`,
`notes/`, `reports/`, implementation directories, and additional parent content.
Their presence, absence, and internal shape are owned by the relevant parent
contract or directory document; this minimum does not claim to be a complete
repository shape.

## Surface の意味

### Symlink

Symlink は、AgentCanon にある shared source を親レポから同じ内容として参照
するために使います。Symlink 先を親レポ固有の内容で上書きせず、変更は
AgentCanon source の topic branch と PR から行います。

- `AGENTS.md`: root runtime instruction の view。
- `.codex/config.toml`: shared Codex runtime config の view。
- `tools/agent-canon`: shared automation の唯一のAgentCanon view。

### Regular directory / file

Regular surface は親レポが ownership を持ち、親固有の責務や state を保持する
ために使います。AgentCanon の source を親の regular copy として二重管理する
ためのものではありません。

- `.devcontainer/`: 親固有 source と regular `devcontainer.json` の実体 directory。
- `.codex/`: parent config overlay と project-specific skill の容器。AgentCanon が
  投影するのは `.codex/config.toml` だけです。
- `.agents/`、`agents/`: 親が必要に応じて所有する regular runtime/document content。
- `.vscode/`: 親が所有する regular editor content。欠落や追加ファイルは有効です。
- `.github/`: 親レポの workflow、issue、PR automation を所有する regular container。
- `documents/`: 親レポ固有の design / contract と document index。
- `docker/`: 親レポの image / pack / build contract。
- `experiments/`: 実験計画と結果の親レポ固有 surface。
- `notes/`: 親レポ固有の運用・知識・失敗記録。
- `reports/`: generated report と raw evidence の置き場。
- `vendor/agent-canon/`: source を編集しない clean submodule checkout。
- `tools/`: 親固有toolを置ける実体directory。AgentCanon toolは直下へ複製しない。
- `scripts/`: 親レポ固有の bootstrap と project slug 置換。
- `python/`、`src/`、`include/`、`lib/`: 親レポの production implementation。
- `goal.md`: 親レポ固有の current task state。AgentCanon view に戻さない。

`.devcontainer/parent-environment.sh` と
`.devcontainer/parent-environment.toml` は optional pair です。両方がない状態は
parent environment 無効として成立します。有効にする場合は両 path を宣言し、各 path
が regular file または regular file へ解決できる Symlink であることを必要条件にします。
片方だけの宣言と、実体がない・file 以外へ解決する Symlink は失敗です。shell file は
親環境の値の唯一の source、TOML は ordered variable names のみを持つ manifest であり、
validator は shell を実行せず、許可された export line と TOML の順序付き name を
完全一致させます。

## Directory owner document

この README は root の境界だけを定義します。各 directory の子構造、役割、更新
手順は次の owner document を参照し、ここへ再掲しません。

- `AGENTS.md`、`.codex/`、`tools/`: `../SHARED_RUNTIME_SURFACES.md` と各 directory の README。
- `.agents/`、`agents/`: 親レポの project owner document（存在する場合）。
- `.devcontainer/`: `../design/devcontainer/parent-devcontainer-policy.md`。
- `documents/parent-repository/`: `CONTAINER_OPERATIONS.md`。
- `.github/`、`.vscode/`、`vendor/`: 親レポの owner document と各 directory の README。
- `documents/`: `../README.md` と `../rule/README.md`。
- `docker/`: `../CONTAINER_OPERATIONS.md` と親レポの `docker/README.md`。
- `experiments/`、`reports/`、`notes/`、project implementation directory:
  親レポ自身の README / design / experiment owner document。

directory に README がある場合、その README は child tree と責務の reader
entrypoint です。README がない場合は、owner document を追加してから child
structure を大きく変更します。構造の説明を root README、親構造 README、
directory README に重複して持たせません。

### Retired paths

`documents/runtime/shared-runtime-surfaces.toml` の `removed_legacy` は、過去の
AgentCanon view が残っている場合にだけ symlink を除去します。親の regular file / directory
は parent-owned content として保持し、個別の editor、devcontainer、GitHub copy を
AgentCanon source から自動生成しません。

## Devcontainer 境界

`.devcontainer/` は親が所有する regular directory です。AgentCanon の active root
projectionには含まれないため、`devcontainer.json` や bootstrap / post-create /
post-attach / Compose generator の有無と内容は親の environment contract が決めます。

- 親の regular `.devcontainer` files は sync で削除・symlink化しません。
- AgentCanon source の standalone devcontainer は source checkout 内で独立して検証します。
- `post-create-parent.sh` は source-root resolver 経由の standalone-source post-create が
  成功した後に呼ぶ親固有 source とする。
- Compose の生成物は親の `.agent-canon/docker-compose.generated.yml` に置く。
- 親 image は #524 canonical contract の digest-pinned plain `ubuntu:22.04` を基礎とし、
  host UID/GID build args `PROJECT_UID` / `PROJECT_GID` から canonical `project`
  user/group を作り、`USER project` で起動する。container-local passwordless sudo は
  mounted dependency の導入にだけ使い、host sudo、host password prompt、host group
  mutation は要求しない。
- 親の default pack が zsh を選ぶ場合、generator は pack の `runtime.shell` を
  process boundary とし、`host-zshrc` profile が明示された場合だけ、resolved regular
  fileであるhost `${HOME}/.zshrc` と resolved regular directoryである `${HOME}/.zsh`
  を canonical sourceからdedicated non-root homeへread-only mountする。欠落・broken
  symlink・型違いはmountを省略し、validatorはresolved absolute source、bind type、
  non-root target、read-onlyを静的に確認する。zsh startupとfresh CIはhost
  zshrc/zsh directoryの有無に依存せず、代替pathは探索しない。
- packの `optional_mount_profiles` と環境 `AGENT_CANON_OPTIONAL_MOUNTS` は、pack順を
  優先したcanonical unionで選択される。`linked-data-roots` は pack-defined inline
  table の repository symlinkを `realpath -e` で確認し、declared `/mnt/<letter>/...`
  targetと一致する既存directoryだけを `read_only: false` の structured bindとして
  投影する。absolute/escape/non-symlink、broad root、重複 source/target、raw
  `runtime.mounts` は拒否し、plain pack/envではhost mountを生成しない。

直接 pack runner は `linked-data-roots` または `docker-host` を明示選択した pack に限って
それぞれの bind を適用し、host zshrc/.zsh など generator 専用の profile を暗黙に再現
しません。`docker-host` の socket が欠落する場合や CLI mount が linked/docker target を
上書きする場合は fail-closed です。

この分離により、active root view の更新と親プロジェクトの hook / build 設定を
別々に review でき、親固有の変更が AgentCanon source の pin を汚染しません。

## Topic workspace

依存 module を変更するときは、親 root の下に次の形で topic workspace を作り、
親レポと依存 module の clone を同じ workspace root に置きます。

```text
<parent-root>/workspace/<topic-slug>/
├── <parent-repo>/
└── <module-basename>/
```

devcontainer は topic root を `/workspace` に一度だけ mount します。親レポと
依存 clone を個別に mount したり、別 topic の clone を runtime に混ぜたり
しません。作業完了後、再現に不要な clone は削除対象ですが、未統合 commit や
ユーザー所有差分がある clone は保持してから判断します。

### Direct-repo exception

依存 module の topic lifecycle 外にある既存 checkout（例:
`~/workspace/data_download`）は `direct-repo` layout として起動できます。この場合、
devcontainer は exact repository root だけを `/workspace/<basename>` に bind し、親の
`~/workspace` 全体、sibling repository、推測した別 path を mount しません。direct-repo
では dependency-module topic marker/status guard を要求・実行しませんが、managed-topic
の guard を弱める経路にはなりません。

generator は `AGENT_CANON_WORKSPACE_LAYOUT=direct-repo` を出力し、post-attach は
`DEPENDENCY_MODULE_CONTAINER_LAYOUT=direct-repo`、
`DEPENDENCY_MODULE_CONTAINER_SOURCE`、`DEPENDENCY_MODULE_CONTAINER_TARGET` を
readback します。direct path の acceptance command は
`devcontainer up --workspace-folder .` です。managed-topic は従来どおり topic root
bind と marker/status guard を使います。

## 構造確認

人間向けの構造確認は `tree` を使います。directory の詳細は各 directory の
README / owner document を読み、ここへ再掲しません。

```bash
tree -a -L <depth> -I '.git|__pycache__|.venv|node_modules|target|reports' <parent-root>
python3 vendor/agent-canon/tools/agent_tools/parent_repo_readiness.py \
  --root <parent-root> --tree-depth <depth>
```

path / mode の判定は `repo_structure_contract.py` と surface manifest checker に
委譲します。README の tree と checker の結果が異なる場合は、まず ownership と
manifest を確認し、Symlink を実体に置き換えて合わせません。

parent environment は optional pair の両方不在、または両方が file 実体へ解決できる
状態を構造上の必要条件にします。readiness や structure checker の pass は、Compose
の runtime behavior、image-owned zsh startup、または parent value の意味が成立した
ことを単独では証明しません。
