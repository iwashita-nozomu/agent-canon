<!--
@dependency-start
contract design
responsibility Parent/standalone devcontainer wrapper boundaryを定義する。
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership and topology
upstream design ../../runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface manifest
upstream design ../../github-first-module-and-devcontainer-policy.md devcontainer ownership boundary
downstream implementation ../../../tools/agent_tools/surface_manifest.py materializes and checks shared surface entries
downstream implementation ../../../tools/sync_agent_canon.sh materializes AgentCanon root views
downstream implementation ../../../.devcontainer/generate-runtime-compose.sh generates runtime compose
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py checks parent repository readiness
@dependency-end
-->

# 親/Source 分離のdevcontainer構成方針

## 責務境界

この設計では、`devcontainer` の共有実装を次の2レイヤーに分離する。

- AgentCanon Source 側（`vendor/agent-canon/.devcontainer`）
  - 共有 runtime スクリプト本体（`post-create.sh` / `post-attach.sh` / `bootstrap-shared-runtime.sh` / `finalize-shared-runtime.sh`）
  - `generate-runtime-compose.sh`
  - 共有 `devcontainer.json`
- 親リポジトリ側（親 root の `.devcontainer/`）
  - wrapper script（親 hook と Source 呼び分け）
  - 親固有 `post-create-parent.sh`（任意）
  - `post-create.sh` が親固有 hook を呼ぶ

## 完成構造

1. 親 root の `.devcontainer` は親固有の実ディレクトリ（`regular`）として存在する。
2. `.devcontainer/devcontainer.json` は AgentCanon source の
   `vendor/agent-canon/.devcontainer/devcontainer.json` への symlink。
3. 親 wrapper は、自身の `BASH_SOURCE[0]` から `script_dir` と `repo_root`
   を求め、`$repo_root/vendor/agent-canon/.devcontainer/<script>` を呼び出す。
   wrapperの相対参照は、親root内の `vendor` をwrapperの配置場所から解決する
   意味であり、process cwdには依存しない。
4. `post-create.sh` の順序保証
   - `vendor/agent-canon/.devcontainer/post-create.sh` を先に実行。
   - 成功時のみ `script_dir/post-create-parent.sh` を同引数で実行。
   - 失敗時は親 hook を呼ばない。

この順序は、共有 runtime identity（finalize）を必ず先行させるための要件。

## Standalone と Parent のパス解決

- Standalone source（`agent-canon` 単体）
  - `generate-runtime-compose.sh` は自身の場所から source root を求め、未指定時は
    source root の `.devcontainer/docker-compose.generated.yml` を生成する。
- Parent root
  - `devcontainer.json` は親rootから実行される前提で、`initializeCommand` と
    `postAttachCommand` は親 `.devcontainer` wrapperを通る。
  - wrapperは自身の `BASH_SOURCE[0]` から親rootを求め、AgentCanon generatorを
    呼び出す。
  - generatorには
    `AGENT_CANON_DOCKER_COMPOSE_OUTPUT=$repo_root/.devcontainer/docker-compose.generated.yml`
    を絶対pathで渡す。これにより、relative defaultをvendor repo rootへ誤解決しない。

### Wrapperの標準形

wrapperの配置場所は親rootの `.devcontainer/` です。全wrapperは次の形で
`script_dir` と `repo_root` を解決し、実行時cwdを参照しません。

```bash
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
bash "${repo_root}/vendor/agent-canon/.devcontainer/post-attach.sh" "$@"
```

`post-create.sh` は標準scriptを先に実行し、成功後だけ親hookを呼び出します。
親hookは `script_dir/post-create-parent.sh` として解決します。

```bash
bash "${repo_root}/vendor/agent-canon/.devcontainer/post-create.sh" "$workspace"
parent_hook="${script_dir}/post-create-parent.sh"
if [ -f "$parent_hook" ]; then
  bash "$parent_hook" "$workspace"
fi
```

## 禁止する構成

- `.devcontainer` 全体を symlink で共有する構成。
- 親独自 hook を共有標準 hook の前に呼ぶ構成。
- 生成 Compose を親側で意図せず別 path へ放置する構成。

## compose 出力先の受け取り設計

`generate-runtime-compose.sh` は以下を受け取る。

- `AGENT_CANON_DOCKER_COMPOSE_OUTPUT`（未指定時は既定の
  `.devcontainer/docker-compose.generated.yml`）
- 親 wrapper から呼ぶ場合は `AGENT_CANON_DEVCONTAINER_REPO_ROOT` に親レポの
  root を渡す。これにより generator の実体位置ではなく、親レポを compose と
  topic workspace root の基準にできる。

相対 path は `${repo_root}` からの相対で解決する。

## 親 hook 契約

`post-create-parent.sh` は任意。
存在しない場合は成功扱い。
存在する場合、上位エントリポイント `post-create.sh` 末尾で同じworkspace引数を
渡して呼び出される。標準post-createが失敗した場合、親hookは呼び出されず、
親hookの失敗はpost-create全体の失敗になる。
