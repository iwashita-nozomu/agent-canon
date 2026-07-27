<!--
@dependency-start
contract reference
responsibility AgentCanon 固有の更新、公開、親レポ投影の文書入口。
upstream design ../README.md documents 索引と正本境界。
downstream design ./agent-canon-update-route.md AgentCanon 更新経路。
downstream design ./agent-canon-parent-repo-latest-checklist.md 親レポ反映確認。
@dependency-end
-->

# AgentCanon 運用

この directory は AgentCanon 自身の source、branch、remote、submodule pin、親レポ
投影を扱います。親レポ固有の設計や実験結果はここへ置きません。

## 構成

- `agent-canon-update-route.md`: source PR から親 pin までの更新経路。
- `agent-canon-parent-repo-latest-checklist.md`: 親レポ反映後の確認。
- `agent-canon-github-remote.md`: canonical remote と公開境界。
- `agent-canon-submodule-rollback.md`: pin rollback の手順。
- `agent-canon-subtree-migration.md`: legacy subtree からの移行。
- `agent-canon-update-tasks.toml`: 機械可読な更新 TODO。
- `template-agent-canon-audit-resolution.md`: 監査指摘の解決記録。
- `agent-canon-licensing-policy.md`: AgentCanon と親レポのライセンス境界。

各ファイルは個別の責務を持つため、同じ手順をこの README に複製しません。
