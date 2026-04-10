# Engineering Avoidances

この note は、repo-wide に何度も読み返す avoid list を短く固定します。

## Avoid

- 会話だけを根拠に実装、設計変更、文書改訂へ進める
- 承認済み design packet があるのに、文書を読まず会話文脈、記憶、推測で実装する
- `Implementation Source Packet` や `Design-To-Implementation Trace` がないまま worker が編集を始める
- design artifact path、design section、test plan item、request clause ID を引用できない実装 slice を進める
- design packet と repo docs / code の矛盾を worker がその場で解釈して実装する
- `documents/`、`notes/`、`references/` の context sweep をせずに着手する
- `python/`、`tests/`、`src/`、`include/`、`lib/`、`tools/`、`scripts/` の reuse sweep をせずに新しい file や module を増やす
- 過去ログ由来の user trait を、今回 request、repo/code precedent、domain/external constraint、unknown/open question と分けずに task requirement へ混ぜる
- notes、guardrails、documents、prior logs、local code / tests で解決できる曖昧さを調べずにユーザーへ戻す
- unknown や open question を silent assumption に変換して要件を埋める
- active な must-do、must-not-do、completion-evidence clause に `unknown_or_open_question` を残す
- Spark を要件定義、詳細設計、重要レビュー、最終判断に使う
- chunk、slice、checkpoint、subpass の完了を user request 全体の完了として報告する
- remaining planned work units や active clause が残っているのに closeout を unlock する
- 最初の update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言しない
- repo-changing task で run bundle と explicit stage activation を省略する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務する
- 学術文章で `notation_definition_reviewer` や `logic_gap_reviewer` を立てずに author 自己判断だけで閉じる
- review feedback を反映せずに次段へ handoff する
- 正本を更新せずに runtime entrypoint だけ直す
- host-global install を repo の正本手順にする
- repo-local virtual environment を作る。`python3-venv`、`python -m venv`、`virtualenv`、`conda create`、`uv venv`、`pipenv`、`poetry env` を使う
- agent helper、CI、review、validation、container runner、experiment helper を root `scripts/` に置く
- partial run を正式結果として扱う
- spot run、debug run、smoke run を比較表、method 採否、正式 report、review evidence に使う
- correctness evidence と performance evidence を混同する
- raw failure count だけを見て、environment noise、case mix、failure kind を分離せずに解釈する
- success case だけを集計して、failure case、worst case、trade-off を落とす
- ordered difficulty 軸を飛び飛びに測って frontier や failure onset を結論する
- code change、protocol change、XLA / runtime flag change を 1 つの iteration に混ぜる
- 実験 script 側で runner、scheduler、GPU slot 管理、timeout cleanup、pid registry、monitoring loop を重複実装する
- 実験 script 側で `CUDA_VISIBLE_DEVICES`、`JAX_PLATFORMS`、`XLA_*` を場当たり的に組み立てる
- protocol にない ad hoc output path、手作業 rename、partial-run resume protocol を増やす
- user request が generic path の usable smoke を求めているのに、specialized path の tuning だけで完了扱いにする
- scope で禁止された runner 変更、function fusion、別経路追加を、性能改善のために横滑りで入れる
- user request clause にない実装 slice を「ついで」として入れる
- 詳細設計または明白な局所 precedent にない variable、function、class、file、CLI flag、config key、public API identifier を worker が自由裁量で作る
- worktree scope を更新せずに編集範囲を広げる
- stale または別 branch / 別 path の `WORKTREE_SCOPE.md` を現在の worktree に流用する
- `WORKTREE_SCOPE.md` の `Editable Directories` 外や `Read-Only Or Avoid Directories` 内を編集する
- scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断を action log に残さず進める
- raw 結果だけ残して、読み方や判断を note / report に落とさない
- JAX の任意 callable を current native runtime が直接理解できるものとして扱う
- generic callable path、specialized coeff path、export-based generic path を 1 つの実装 slice で混同する
- generic path の完了条件を specialized coeff path の evidence だけで満たした扱いにする
- export worker に live Python object reference を渡す。cross-process 境界では serializable manifest と reconstruction recipe を使う
- runtime materialization を compile DAG node として扱う。`LoadedProgram` は runtime vertex / lifetime scope に属する
- external runner が process model を持つのに、bridge-local な追加 process spawn を足す
- small toy、dense Jacobian、baseline 未比較の結果から trainer replacement、scalability、superiority、広い theorem を主張する
- 理論 note が一般 weighted case の正しい抽象でないと示した unrestricted permutation-group enumeration を継続投資対象にする
- failure-onset dimension を記録せず、implementation bug と真の frontier limit を混同する
- `notes/` に置くべき一時メモを `documents/` へ混ぜる
- validation を飛ばして commit / push だけ進める
- required review、validation、commit / push を省略して完了扱いにする

## Source

- 2026-04-10 に `/mnt/git/agent-canon.git`、`/mnt/git/experiment_runner.git`、`/mnt/git/jax_util.git`、`/mnt/git/server_develop.git`、`/mnt/git/template.git` と対応する `/mnt/l/workspace/*` の `documents/`、`notes/`、worktree logs を検索して抽出しました。

## When To Re-Read

- 新しい worktree を切った直後
- Docker、CI、dependency を更新する前
- 実験 loop を閉じる前
- repo-wide な workflow 整理を始める前
