# Experiment Result JSON Archive
<!--
@dependency-start
responsibility Documents Experiment Result JSON Archive for this repository.
upstream design ../README.md notes lifecycle index
@dependency-end
-->


このディレクトリには、`main` に持ち帰る最小限の final JSON を置きます。

- 目的は、後から別の図や集計を再生成できるようにすることです。
- raw な JSONL、巨大ログ、途中経過の全ファイルまでは置きません。
- branch を代表する完走 run の final JSON を選んで置きます。
- 何を `main` に残し、何を隔離場所に残したかは、対応する note から辿れるようにします。
- partial run は診断用の artifact に留め、`main` の canonical archive には置きません。

各 JSON について、対応する note から次を辿れるようにします。

- branch 名
- 元の results branch または隔離場所
- 元データの所在
- その JSON を持ち帰った理由
