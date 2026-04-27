# Theme Notes
<!--
@dependency-start
upstream design ../README.md notes lifecycle index
@dependency-end
-->


`notes/themes/` には、複数の実験や調査から得た知見を話題ごとにまとめます。

`notes/experiments/` が個別実験の report と解釈を扱い、`notes/knowledge/` が短い実務メモを扱うのに対し、このディレクトリでは「その話題について今何が言えるか」を topic 単位で整理します。self-learning と対話由来の durable memory は `memory/` を正本にし、この directory は topic synthesis を主に扱います。

## 役割

- 個別実験の結果を一般化して残す
- うまくいった工夫と失敗した工夫を分けて残す
- 再利用しやすい設計上の注意点をまとめる

## 形式

- 1 theme 1 file を基本とします
- 歴史の全記録ではなく、現時点の知識として再利用したい項目を優先します
- `Known`, `Likely`, `Open` に加えて `Worked`, `Did Not Work`, `Coding Pattern`, `Pitfall` のようなラベルを使えます
- うまくいかなかった案も、なぜやめたかとどこで詰まったかが分かる形で残します
- 観測ベースの知見と文献ベースの知見が混ざるときは区別できるようにします
- 本文では branch 名や一時的な運用名をできるだけ主語にしません
- 方法そのものを主語にし、内部履歴は `References` や `diary/` に回します
- worktree action log や experiment note から昇格させるときは、個別 run の順序ではなく theme ごとにまとめ直します

## Template

- [THEME_NOTE_TEMPLATE.md](/mnt/l/workspace/project_template/notes/themes/THEME_NOTE_TEMPLATE.md)
- [USER_PREFERENCES.md](/mnt/l/workspace/project_template/memory/USER_PREFERENCES.md)
  - 会話から抽出した user preference の固定入口です。shared canon `memory/` を正本にし、十分に安定した項目だけを `AGENTS.md` へ昇格します。`notes/themes/USER_PREFERENCES.md` は互換 view です。
- [AGENT_PHILOSOPHY.md](/mnt/l/workspace/project_template/memory/AGENT_PHILOSOPHY.md)
  - agent の作業哲学、対話から得た学習、task retrospective の固定入口です。shared canon `memory/` を正本にし、十分に安定した項目だけを workflow、guardrail、`AGENTS.md` へ昇格します。`notes/themes/AGENT_PHILOSOPHY.md` は互換 view です。
