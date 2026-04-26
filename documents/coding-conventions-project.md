<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# プロジェクト全体の運用規約

この文書は、テンプレート repo 全体に共通する高レベル方針をまとめます。

## 1. 対象

- 対象は repo 全体です。
- 言語や実装形態に依らず、実装、実験、文書、補助スクリプトを同じ原則で扱います。

## 2. ディレクトリの考え方

- `documents/` は正本です。
- `notes/` は知見、比較メモ、補助整理です。
- `agents/` はエージェント運用の正本です。
- `tools/` は shared automation の正本です。agent helper、CI / review / validation、container runner、experiment helper、Markdown helper はここに置かなければなりません。
- `scripts/` は repo-local bootstrap の入口です。template 固有の初期化、slug 置換、bare remote 初期化だけをここに置かなければなりません。
- `docker/` は共通開発環境の定義です。
- `experiments/` は実験コードと生成物の置き場です。
- `python/`, `src/`, `include/`, `lib/` は実装スロットです。全部を使う必要はありません。
- C++ を使う場合の build layout は `documents/cpp-build-layout.md` を正本にします。
- Bash 実装は用途で置き場所を固定します。shared automation の Bash は `tools/`、repo-local bootstrap の Bash は `scripts/` に置かなければなりません。

## 3. 文書運用

- `documents/` には正本だけを置きます。
- 実装変更でルールや設計が変わる場合は、対応する文書を同じ変更で更新します。
- Markdown を編集したら、対象の `.md` に `mdformat` を適用し、その後で `make docs-check` を通さなければなりません。
- 上の Markdown 運用は `documents/`、`tools/`、`scripts/`、`.github/`、root `README.md`、`QUICK_START.md` を含む正本文書に適用します。
- 日付付きの途中報告、個別メモ、比較の試行錯誤は `notes/` に置きます。
- agent team の要約は `agents/README.md` に集約し、他の入口へ複製しません。

## 4. 開発環境

- 共通実行環境が必要な場合は `docker/` を基準にします。
- Python 依存を追加する場合は `docker/Dockerfile` と `docker/requirements.txt` を同時に更新します。
- `docker/Dockerfile` または `docker/requirements.txt` を更新した変更では、`make docker-build-check` を必須にします。
- 開発環境の更新では、必要な README と運用文書も同じ変更で更新します。
- Python を使う場合でも、repo 全体の入口を Python 専用にはしません。
- canonical container の `safe.directory` は Docker image 側で明示設定しなければなりません。run-time entrypoint や ad hoc env だけで後付けすることを禁止します。
- template の canonical Dockerfile では、`/workspace` と local bare remote 置き場 `/mnt/git/*.git` に必要な `safe.directory` を build 時の `git config --global --add safe.directory ...` で正本化しなければなりません。
- Docker container 内から Docker を使う手順を正本にする場合は、同梱するのは CLI だけとし、host socket mount または別 daemon が必要であることを文書へ明記しなければなりません。
- canonical container では `tools/ci/check_fresh_clone.sh` が使う `rsync` を `docker/Dockerfile` に同梱しなければなりません。host runtime で `rsync` が無い場合は script の fallback で検証を継続できますが、Dockerfile 側の欠落を放置してはいけません。

## 4.5 環境依存ツール導入提案のルール

- repo-wide に使う環境依存ツールの導入提案では、`agents/templates/environment_change_proposal.md` を使って理由、影響範囲、validation、rollback を記録しなければなりません。
- host-global install を repo の正本手順として採用することを禁止します。
- repo-wide に必要な Python tool は、原則として `docker/requirements.txt` と `docker/Dockerfile` に同時反映しなければなりません。
- CI でも使う tool を、手元だけの補助 install として導入することを禁止します。
- 1 回限りの調査や個人補助にとどまる tool は、repo 正本へ追加する前に container 実行、checked-in script、既存依存で代替できないか確認しなければなりません。
- 導入提案では、少なくとも次を明記しなければなりません。
  - 何の workflow を支えるのか
  - host / Docker / CI のどこを更新するのか
  - `docker/Dockerfile` と `docker/requirements.txt` の更新要否
  - どのコマンドで validate するのか
  - 不採用または撤回するときの rollback 手順

## 4.6 Docker 更新時の扱い

- `docker/Dockerfile` を更新する変更では、依存追加の有無にかかわらず `README.md`、`QUICK_START.md`、関連する `documents/` の command や説明も同じ変更で見直さなければなりません。
- Docker 変更で新しい tool を同梱する場合は、その tool の用途、呼び出し入口、不要になったときの削除方針を文書へ残しなければなりません。
- Docker runtime の再利用 surface は `docker/packs/*.toml`、`docker/codex-container-profiles.toml`、`docker/python-execution-rules.toml` を正本にし、script 側へ path 分岐を埋め込んではなりません。
- main server host の path、mount、builder 前提は `documents/server-host-contract.md` と `documents/templates/server_runtime_layout.template.toml` を正本にし、口頭運用にしてはなりません。
- C++ / JAX export を使う場合の canonical CMake entrypoint は root `CMakeLists.txt` です。`src/` や `include/` の下に別 root を増やすことを禁止します。
- template 既定の C++ 実装形態は header-only です。`include/` を実装の主置き場にし、`src/` は特例実装だけに使います。
- C++ build は必ず out-of-source にし、`build/cpp/<profile>/` を使わなければなりません。
- 再利用する local install tree は `.state/cpp-install/<profile>/`、再利用する local `jax.export` artifact は `.state/jax-export/<profile>/` に置かなければなりません。

## 5. テストとレビュー

- 実装変更には、対応するテストまたは検証手順を同じ変更でそろえます。
- 仕上げ前に `make ci-quick`、必要に応じて `make ci` を流します。
- 文書変更ではリンク切れと記述の入口整合を確認します。

## 6. 実験運用

- 実験コードと生成物は `experiments/` 配下に集約します。
- 1 回の run は fresh 実行として扱います。
- partial run を正式結果として継ぎ足しません。
- 複数 run をまたぐ知見は `notes/experiments/` または `notes/themes/` に残します。
- topic ごとの report を top-level `reports/` に置きません。

## 7. branch 方針

- 既定の統合先は `main` です。
- 恒常的な branch 分割は行いません。
- 短期 branch は、レビューや安全な切り分けが必要なときだけ使います。
- 統合が済んだ branch は削除し、運用知識は `documents/` か `notes/` に吸収します。

## 8. 規約文の書き方

- 禁止事項は `禁止` と明記します。
- 必須事項は `必須` または `しなければなりません` と書きます。
- 曖昧な規範表現で運用ルールをぼかしません。
