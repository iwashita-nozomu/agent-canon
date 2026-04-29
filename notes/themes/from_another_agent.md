# From Another Agent
<!--
@dependency-start
responsibility Documents From Another Agent for this repository.
upstream design README.md notes lifecycle index
@dependency-end
-->


この note は、前の agent session から次の agent へ持ち越す TODO と、
optional follow-up 候補を短く残すための cross-run 申し送りです。
正式ルールに昇格した内容は `agents/` か `documents/` へ移し、
ここには「次に読む価値がある carry-over」だけを残します。

## Current Focus

- いま cross-run で持ち越す内容がある場合だけ更新します。
- 正本へ昇格した内容はこの section に残しません。

## やるべきこと

- ここに次の agent が読むべき carry-over TODO を短く書きます。
- `Current issue:` と `Next safe step:` を書けると十分です。

## お勧め機能

- 今回の task と隣接していて、scope を壊さずに採用できる候補だけを書きます。
- repo-wide rule に昇格したら、ここから消して正本へ移します。

## Update Rule

- この note は短く保ちます。
- 反復参照される規則は `agents/` か `documents/` に昇格します。
- 完了した項目を消すと文脈が飛ぶ場合だけ、理由つきで短く更新します。
