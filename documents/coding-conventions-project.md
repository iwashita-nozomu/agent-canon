<!--
@dependency-start
contract policy
responsibility Documents プロジェクト全体の運用規約 for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./github-first-module-and-devcontainer-policy.md GitHub-first module and devcontainer boundary policy
upstream design ../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream implementation ../tools/agent_tools/check_convention_compliance.py validates legacy forwarder warning policy
downstream implementation ../tools/agent_tools/convention_compliance_contracts.toml declares convention marker contracts
@dependency-end
-->

# プロジェクト全体の運用規約

この文書は、テンプレート repo 全体に共通する高レベル方針をまとめます。

## この文書の読み方

この文書は、repo 全体の対象、directory responsibility、文書運用、開発環境、環境依存 tool 導入、Docker 更新、legacy forwarder、運用境界、テストとレビュー、実験、branch、規約文、checker contract surface を説明します。まず対象とディレクトリの考え方を読み、変更種別に応じて文書運用、開発環境、テスト、実験、branch の章へ進みます。規約文と checker contract は、正本文書や validation rule を更新するときに確認します。

## 1. 対象

- 対象は repo 全体です。
- 言語や実装形態に依らず、実装、実験、文書、補助スクリプトを同じ原則で扱います。

## 2. ディレクトリの考え方

- `documents/` は正本として扱います。
- `notes/` は知見、比較メモ、補助整理です。
- `agents/` はエージェント運用の正本です。
- `tools/` は shared automation の正本です。agent helper、CI / review / validation、container runner、experiment helper、Markdown helper はここに置きます。
- `scripts/` は repo-local bootstrap の入口です。template 固有の初期化、slug 置換、bare remote 初期化だけをここに置きます。
- `docker/` は template / project の runtime image、build library、dependency pack の定義です。
- `.devcontainer/` は AgentCanon-owned shared runtime ergonomics です。Codex、agent 用 npm / Node、GitHub CLI / `gh`、auth mount、attach status はここで扱います。
- `experiments/` は実験コードと生成物の置き場です。
- `python/`, `src/`, `include/`, `lib/` は実装スロットです。全部を使う必要はありません。
- C++ を使う場合の build layout は `documents/cpp-build-layout.md` を正本にします。
- Bash 実装は用途で置き場所を固定します。shared automation の Bash は `tools/`、repo-local bootstrap の Bash は `scripts/` に置きます。

## 3. 文書運用

- `documents/` には正本だけを置きます。
- 実装変更でルールや設計が変わる場合は、対応する文書を同じ変更で更新します。
- 正本文書の claim grounding では、実装 path、設定 surface、checker / tool
  output、proof obligation、外部 source packet、または run-local planning evidence の
  evidence class を明示します。
- 実装由来 claim は `program contract` として public entrypoint、入力 schema、
  runtime profile、return projection、observable effect、assumptions / preconditions、
  validation command を示します。
- 長めの reader-facing Markdown は、先頭付近に文書内容、主な章のまとまり、
  読むべき場面、誤用を避ける境界を示す reader map を置きます。詳細は
  `documents/conventions/common/05_docs.md` を正本にします。
- Markdown を編集したら、対象の `.md` に formatter を適用し、その後で `tools/bin/agent-canon docs check` を通します。
- 上の Markdown 運用は `documents/`、`tools/`、`scripts/`、`.github/`、root `README.md`、`QUICK_START.md` を含む正本文書に適用します。
- 日付付きの途中報告、個別メモ、比較の試行錯誤は `notes/` に置きます。
- agent team の要約は `agents/README.md` に集約します。

## 4. 開発環境

- 共通実行環境が必要な場合は、`CONTAINER_OPERATIONS.md` を正本として repo-local `docker/` と AgentCanon-owned `.devcontainer/` の責務を分けます。
- Python 依存を追加する場合は `docker/requirements.txt` と `docker/install_python_dependencies.sh` の契約を基準にします。Python requirements の install / copy はこの 2 ファイルルートで実施し、`docker/Dockerfile` はその処理を担わない運用です。
- `docker/Dockerfile` または `docker/requirements.txt` を更新した変更では、`make docker-build-check` を実行します。
- 開発環境の更新では、必要な README と運用文書も同じ変更で更新します。
- Python を使う場合でも、repo 全体の入口は language-neutral に保ちます。
- canonical container の `safe.directory` は `docker/register_safe_directories.sh` で管理します。Docker image build 時は repo workspace の `/workspace` を登録し、devcontainer 作成時や smoke test では mount 済み workspace の `vendor/*` を列挙して `/workspace/vendor/<name>` を動的に登録します。
- Template / AgentCanon 固有の machine-local remote path は `documents/template-github-remote.md` と `documents/agent-canon-github-remote.md` を正本にします。
- Docker container 内から Docker を使う手順を正本にする場合は、同梱する CLI、host socket mount、または別 daemon の要件を文書へ明記します。
- canonical container では `tools/ci/check_fresh_clone.sh` が使う `rsync` を `docker/Dockerfile` に同梱します。host runtime で `rsync` が不足する場合は、環境構築手順で `rsync` を導入してから同じ検証を再実行します。
- Codex CLI、agent 用 npm / Node、GitHub CLI / `gh`、auth setup、host mount 方針の具体的な境界、例外、validation は `CONTAINER_OPERATIONS.md` を正本にします。

## 4.5 環境依存ツール導入提案のルール

- repo-wide に使う環境依存ツールの導入提案では、`agents/templates/environment_change_proposal.md` を使って理由、影響範囲、validation、rollback を記録します。
- host-global install 由来の要件は、必要時に `CONTAINER_OPERATIONS.md` または `docker/` の運用境界へ反映します。
- repo-wide に必要な Python tool は、原則として `CONTAINER_OPERATIONS.md` の Python dependency rule と repo-local installer contract に反映します。Dockerfile へ入れるのは OS package、runtime library、build tool、image-level helper だけです。
- CI でも使う tool は手元だけの補助 install に留めず、共有運用手順へ反映してから利用します。
- 1 回限りの調査や個人補助にとどまる tool は、repo 正本へ追加する前に container 実行、checked-in script、既存依存での代替可否を確認します。
- 導入提案では、少なくとも次を明記します。
  - 何の workflow を支えるのか
  - host / Docker / CI のどこを更新するのか
  - `docker/Dockerfile`、`docker/requirements.txt`、`.devcontainer/` の更新要否
  - どのコマンドで validate するのか
  - 不採用または撤回するときの rollback 手順

## 4.6 Docker 更新時の扱い

- `docker/Dockerfile` を更新する変更では、依存追加の有無にかかわらず `README.md`、`QUICK_START.md`、関連する `documents/` の command や説明も同じ変更で見直します。
- Docker 変更で新しい tool を同梱する場合は、その tool の用途、呼び出し入口、不要になったときの削除方針を文書へ残します。
- Docker 変更で agent convenience tool が必要になった場合は、`CONTAINER_OPERATIONS.md` の devcontainer boundary に従って AgentCanon-owned `.devcontainer/post-create.sh` を更新します。
- Docker runtime の再利用 surface は `docker/packs/*.toml`、`docker/codex-container-profiles.toml`、`docker/python-execution-rules.toml` を正本にし、path 分岐は各 surface の契約へ集約します。
- Docker runtime、runtime pack、devcontainer 生成導線を変えた場合は `python3 tools/ci/container_config.py` を通し、`docker/Dockerfile`、`docker/packs/*.toml`、`.devcontainer/` の整合を確認します。
- main server host の path、mount、builder 前提は `documents/server-host-contract.md` と `documents/templates/server_runtime_layout.template.toml` を正本にし、実行経路を都度記録して共有します。
- C++ を使う場合の canonical CMake entrypoint は root `CMakeLists.txt` です。`src/` や `include/` の下に別 root を増やす場合は、まず `CMakeLists.txt` を維持したままの代替設計が成立するかを確認し、追加 root が必要な場合は run bundle で理由を示します。
- template 既定では C++ 実装を持ちません。C++ を追加する project では `include/` を実装の主置き場にし、`src/` は特例実装だけに使います。
- C++ build は out-of-source とし、`build/cpp/<profile>/` を使います。
- 再利用する local install tree は `.state/cpp-install/<profile>/` に置きます。optional な local `jax.export` artifact は用途名を含む `.state/<project>/...` 配下に分離します。

## 4.7 Legacy Forwarder Migration Rule

- legacy forwarder / migration wrapper は `LEGACY_FORWARDER_WARNING_REQUIRED` marker を持ちます。
- legacy forwarder / migration wrapper は実処理へ進む前に stderr へ caller chain、canonical command、`fix-now` severity、移行後に元 task へ戻る prompt message を出します。
- agent は `*_FORWARDER=deprecated`、`*_FORWARDER_SEVERITY=fix-now`、または caller chain 付きの移行警告を見たら、先に呼び出し元を canonical command へ移行します。
- 移行に追加判断が要る場合は、警告の caller chain と移行先 command を run bundle、issue、または PR body に blocker として残します。

## 運用境界

- repo 固有の Template / AgentCanon mirror path は `documents/template-github-remote.md` / `documents/agent-canon-github-remote.md` へ集約します。
- Codex CLI、agent 用 npm / Node、GitHub CLI / `gh`、auth setup、host mount 方針は `CONTAINER_OPERATIONS.md` の手順で扱います。
- host-global install 由来の要件は `CONTAINER_OPERATIONS.md` / `docker/` の更新対象として収束させます。
- CI でも使う tool は、共有運用ルートへ反映して運用します。
- `src/` や `include/` の下に別 CMake root を増やす場合は、`run bundle` に代替根拠を先に置いてから進めます。原則は `CMakeLists.txt` を基準に継続します。
- legacy forwarder / migration wrapper が出した `fix-now` 移行警告は、移行方針を示した `run bundle` / `issue` / PR body を blocker として残してから作業再開します。

## 5. テストとレビュー

- 実装変更には、対応するテストまたは検証手順を同じ変更でそろえます。
- 仕上げ前に `make ci-quick`、必要に応じて `make ci` を流します。
- 文書変更ではリンク切れと記述の入口整合を確認します。
- legacy forwarder / migration wrapper の warning policy は `python3 tools/agent_tools/check_convention_compliance.py` で確認します。

## 6. 実験運用

- 実験コードと生成物は `experiments/` 配下に集約します。
- 1 回の run は fresh 実行として扱います。
- 正式結果は planned run と acceptance criteria が揃った実行から採用します。
- 複数 run をまたぐ知見は `notes/experiments/` または `notes/themes/` に残します。
- topic ごとの report は canonical artifact placement に従って配置します。

## 7. branch 方針

- 既定の統合先は `main` です。
- branch 分割は短期レビュー、切り分け、保護 surface の調整に使います。
- 短期 branch は、レビューや安全な切り分けが必要なときだけ使います。
- 統合が済んだ branch は削除し、運用知識は `documents/` か `notes/` に吸収します。

## 8. 規約文の書き方

- 規約の分類は `必須`、`許可`、`任意`、`受け入れ条件`、`完了条件`、`例外` で明示します。
- 必須事項は `必須`、`必要です`、`実行します` などの肯定形で書きます。
- 運用ルールは具体的な実行条件、検証条件、記録先で表します。

## 9. Checker Contract Surface

- checker が文書、skill、workflow の marker contract を検査する場合、marker
  一覧は `tools/agent_tools/convention_compliance_contracts.toml` に置きます。
- Python checker 本体は contract manifest の読み込み、path 解決、finding
  出力を担当します。
- tool、hook、checker の warning は、free-form note ではなく
  `tool_warning_ledger`、`warning_id`、`source_tool`、`severity`、
  `repair_command`、`tool_warning_exit_status` を持つ closeout obligation として
  記録します。
