# Theme Notes

`notes/themes/` には、複数の実験や調査から得た知見を話題ごとにまとめます。

`notes/experiments/` が個別実験の report と解釈を扱い、`notes/knowledge/` が短い実務メモを扱うのに対し、このディレクトリでは「その話題について今何が言えるか」を topic 単位で整理します。

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
