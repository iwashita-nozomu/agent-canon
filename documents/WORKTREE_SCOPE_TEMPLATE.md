# WORKTREE_SCOPE Template
<!--
@dependency-start
responsibility Documents WORKTREE_SCOPE Template for this repository.
@dependency-end
-->


このファイルは、他環境へ渡す worktree や、変更範囲を限定して使う worktree のためのテンプレートです。
実際に使うときは、このファイルを worktree root に `WORKTREE_SCOPE.md` として置きます。

## Worktree Summary

- Branch:
- Worktree path:
- Purpose:
- Owner or agent:

## Kickoff Status

- Scope refreshed at:
- Action log path:
- Branch summary path:
- User request contract path:
- Kickoff checks completed:
- Next step after kickoff:

## Editable Directories

- `path/to/dir`
- `another/path`

## Runtime Output Directories

- `experiments/<topic>/result/`
- `experiments/<area>/<topic>/result/`

## Experiment Registry Links

- Registry file: `experiments/registry.toml`
- Topics in scope:
  - `<topic_name>`
- Expected registry metadata to update:
  - `active_branch`
  - `active_worktree`
  - `scope_file`

## Read-Only Or Avoid Directories

- `path/to/avoid`
- `another/path`

## Required References Before Editing

- [documents/worktree-lifecycle.md](worktree-lifecycle.md)
- [documents/notes-lifecycle.md](notes-lifecycle.md)
- [documents/coding-conventions-project.md](coding-conventions-project.md)
- [notes/guardrails/README.md](../notes/guardrails/README.md)
- [notes/failures/README.md](../notes/failures/README.md)
- `documents/<relevant_rule>.md`
- `agents/skills/<relevant_skill>.md`
- `notes/<existing_context>.md`
- `reports/agents/<run-id>/<artifact>.md`
- broad directory 名だけで済ませず、先に読む file を明記する

## Main Carry-Over Targets

- `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md`
- `notes/experiments/<topic>.md`
- `notes/experiments/results/<topic>_<date>.json`
- `notes/branches/<branch_topic>.md`

## Working Notes During Execution

- Action log path: `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md`
- Experiment memo path: `notes/experiments/<topic>.md`
- Branch summary path: `notes/branches/<branch_topic>.md`
- User request contract path: `reports/agents/<run-id>/user_request_contract.md`
- Note template: `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- Append command: `python3 tools/agent_tools/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"`
- When contract path is concrete, the same append command also updates `reports/agents/<run-id>/work_log.md`.
- worktree 内でも、最終配置と同じ相対パスで下書きする

## Required Checks Before Commit

- `pyright`
- `markdownlint`
- `pytest ...`
- `make ci-quick`

## Additional Rules

- ここに、この worktree 固有の制約を書きます。
- Branch と Worktree path は current state と一致させる。一致しない `WORKTREE_SCOPE.md` を別 worktree へ流用しない。
- `Editable Directories` 外と `Read-Only Or Avoid Directories` 内は編集しない。
- 例: テストは触らない、結果 JSON は commit しない、runner だけ変更する、など。
- 例: 変更した Markdown は `.markdownlint.json` を基準に確認する。
- 例: scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は action log に逐次追記する。各 entry には `request_clause_ids=` を入れる。
- 例: closeout 前に `documents/notes-lifecycle.md` を見て、knowledge/theme/failure へ昇格させる項目を決める。
- 例: branch が複数 session 続く場合は `notes/branches/<branch_topic>.md` を維持する。
