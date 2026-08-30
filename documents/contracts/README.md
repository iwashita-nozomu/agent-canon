<!--
@dependency-start
contract reference
responsibility 親レポが利用する環境、remote、bootstrap、実行境界の契約入口。
upstream design ../README.md documents 索引と正本境界。
downstream design ./static-seed-export.md template consumer向け静的seedの供給境界。
@dependency-end
-->

# 利用契約

この directory は、親レポが AgentCanon を利用するときに選択する環境・remote・
bootstrap・実行契約を置きます。AgentCanon の一般的な構造規約や個別実装はここへ
混在させません。

## 構成

- `derived-repo-bootstrap-runbook.md`: 派生レポの導入手順。
- `github-first-module-and-devcontainer-policy.md`: module と devcontainer の所有境界。
- `ordered_integration_interface.json`: ordered integration の canonical interface contract。
- `linux-wsl-host-requirements.md`: host 環境の前提。
- `remote-execution-repo-contract.md`: remote 実行レポの契約。
- `server-host-contract.md`: server host の契約。
- `static-seed-export.md`: template consumer向けstatic seedの一方向供給契約。
- `static-seed-allowlist.toml`: static seedへ入る唯一のexact-path allowlist。
- `template-bootstrap.md`: template bootstrap の契約。
- `template-github-remote.md`: template の canonical remote。
- `licensing-policy.md`: 親レポの licensing surface。
- `project-template-overview-slides.md`: template 全体の概要。
