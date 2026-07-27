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
@dependency-end
-->

# 親レポの devcontainer 境界

## 最低限の構造

親レポの `.devcontainer/` は親が所有する実ディレクトリです。最低限、次だけを
固定します。

- `.devcontainer/devcontainer.json` は
  `vendor/agent-canon/.devcontainer/devcontainer.json` への symlink。
- 親固有の処理がある場合は `.devcontainer/post-create-parent.sh` に置く。
- AgentCanon の共有スクリプトを親 `.devcontainer/` にコピーしたり、wrapper を
  追加したりしない。

この最低限以外の親レポ固有ディレクトリやファイルを禁止しない。構造検査は
この所有境界と symlink の健全性だけを確認し、親レポの拡張余地を奪わない。

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

Compose の生成先は親レポの `.agent-canon/docker-compose.generated.yml` とする。
`.agent-canon/` は親レポの実行状態用であり、生成 Compose を追跡対象にしない。

## post-create の順序

`postCreateCommand` は AgentCanon の共有 `post-create.sh` を先に呼び、成功した
後に親固有の `post-create-parent.sh` を直接呼ぶ。共有処理が失敗した場合は親固有
処理へ進まない。親固有処理の失敗も devcontainer 作成の失敗として扱う。

## 禁止する重複

- `.devcontainer` 全体を symlink にする。
- AgentCanon の共有 script を親側へコピーする。
- 共有 script を呼ぶだけの親 wrapper を作る。
- 生成 Compose を `.devcontainer/` と `.agent-canon/` の両方へ作る。

AgentCanon の共有実装を変更するときは AgentCanon source clone で変更し、PR を
`main` に統合してから、親レポの submodule pin を更新する。
