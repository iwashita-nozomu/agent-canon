# from_another_agent
<!--
@dependency-start
responsibility Documents from_another_agent for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

前の agent session から引き継ぐ TODO、carry-over、追加候補を短く読み、今回の task に効くものだけを取り込みます。

## Use When

- 前の agent の続きから始める
- cross-run の TODO や carry-over を落としたくない
- note に残っている「お勧め機能」を今回の task に織り込む価値がある

## Core References

- `notes/themes/from_another_agent.md`
- `AGENTS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`

## Expected Outcome

- 今回の task に関係する carry-over TODO が見えている
- 採用する optional follow-up が短く決まっている
- 正本に昇格した内容と note に残す内容が分かれている

## Default Sequence

1. `notes/themes/from_another_agent.md` を最初に読みます。
1. `## やるべきこと` から、今回の task に直接効く項目だけを抜き出します。
1. `## お勧め機能` は scope を広げすぎない範囲でだけ採用します。
1. 正式ルールに昇格した内容は `agents/` か `documents/` へ移し、この note には carry-over だけを残します。
1. 完了、棚卸し、正本昇格を行った項目は同じ変更で note も更新します。

## Boundary

- repo-wide の恒久ルール更新は `agents/` か `documents/` に書きます。
- 一時的な思いつきだけを長く残す場所には使いません。
