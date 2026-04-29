# user-preference-sync
<!--
@dependency-start
responsibility Documents user-preference-sync for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

`memory/USER_PREFERENCES.md` に蓄積した観測から、repo-wide で durable な user preference だけを `AGENTS.md` へ昇格します。

## Use When

- 会話から得た user preference が増えてきた
- `AGENTS.md` の方針が古くなっている
- provisional と stable を整理したい

## Core References

- `AGENTS.md`
- `memory/USER_PREFERENCES.md`
- `documents/notes-lifecycle.md`
- `agents/canonical/CODEX_WORKFLOW.md`

## Sync Rules

1. `memory/USER_PREFERENCES.md` を読み、重複、反復、明示的な durable preference を cluster します。
1. task 固有の一時指示は `AGENTS.md` へ上げません。
1. repo-wide に効く stable item だけを `AGENTS.md` の短い bullet に昇格します。
1. `AGENTS.md` へ上げた項目は wording を短くし、理由や会話履歴は note 側に残します。
1. note 側では promoted item を消さず、必要なら `Stable Preferences` に寄せ直します。
1. `AGENTS.md` を会話ログで膨らませません。
