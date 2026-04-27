<!--
@dependency-start
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Templates

このディレクトリは、repo 外の設定 root に持ち出して使う canonical template を置く場所です。
実値は host 固有なので commit しませんが、項目名と構造はここを正本にします。

## Remote Execution

- `remote_execution_target.template.toml`
  - 手動登録する SSH target の template
- `remote_execution_repo.template.toml`
  - repo ごとの clone URL と runtime profile の template

## Server Host

- `server_host_inventory.template.md`
  - main server host の inventory と readiness gap を記録する template
- `server_runtime_layout.template.toml`
  - main server host の path、mount、builder 前提を記録する template

## Rule

- host 固有の実値は repo に置きません
- template の key 追加や意味変更は、関連設計文書と同じ変更で行います
- 実値の例は匿名化し、必要なら `notes/` に補助説明を書きます
