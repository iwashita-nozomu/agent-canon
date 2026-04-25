# Agent Communication Protocol
<!--
@dependency-start
upstream design README.md agent canon overview
@dependency-end
-->


この文書は、agent-to-agent handoff と review の正本です。

## 基本ルール

- 次の role が判断に使う情報は artifact に残します。
- reviewer は repo を直接修正せず、required change を artifact に残します。
- review を受けた role は `resolved`、`rejected`、`escalated` のいずれかで必ず応答します。
- scope や permission の変更は `manager` に戻します。

## 主要な通信面

1. `reports/agents/<run-id>/` の role artifact
1. `decision_log.md`
1. `team_manifest.yaml`

run 固有のやり取りは report bundle に残し、repo-wide の正本には持ち込みません。

## Handoff Packet

- `from`
- `to`
- `stage`
- `request_clause_ids`
- `summary`
- `requested_action`
- `artifacts`
- `repo_changes`
- `open_questions`
- `status`

## Review Packet

- `request_clause_ids`
- `finding`
- `severity`
- `required_change`
- `evidence`
- `status`

## Write Scope Packet

- `role`
- `workspace`
- `allowed_paths`
- `forbidden_paths`
- `owned_files`
- `integration_owner`
- `merge_strategy`

write-capable role を複数使う場合は、handoff の前に write scope packet を残します。
同じ file を 2 つの writer に同時に割り当てません。
同じディレクトリを複数 writer が触る場合は、`owned_files` を file 単位で disjoint にします。
file 境界を切れない場合は、同一 workspace の並列 write をやめ、別 worktree へ分けるか parent が直列化します。

## Escalation

次では `manager` へ戻します。

- reviewer と execution role で合意できない
- scope 外の変更が必要
- permission 拡張が必要
- research や experiment だけでは根拠が不足する
- infra change に rollback がない
