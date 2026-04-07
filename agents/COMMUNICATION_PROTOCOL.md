# Agent Communication Protocol

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
- `summary`
- `requested_action`
- `artifacts`
- `repo_changes`
- `open_questions`
- `status`

## Review Packet

- `finding`
- `severity`
- `required_change`
- `evidence`
- `status`

## Escalation

次では `manager` へ戻します。

- reviewer と execution role で合意できない
- scope 外の変更が必要
- permission 拡張が必要
- research や experiment だけでは根拠が不足する
- infra change に rollback がない
