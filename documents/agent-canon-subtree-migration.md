# agent-canon subtree 構成

この文書は、`agent-canon` maintainer が subtree 構成を保守するときの正本です。
template 利用者向けの短い説明は root 側の `documents/agent-canon-subtree-migration.md` を見ます。

## 目的

- `git clone <template>` 直後でも shared canon を使える状態を保つ
- shared canon の source of truth を upstream `agent-canon` repo と `vendor/agent-canon/` snapshot に固定する
- template root には runtime discovery に必要な surface だけを残す
- template 利用者向けの入口文書は root regular file として残す

## 固定構成

- upstream repo:
  - `agent-canon`
- template / 派生 repo 側の snapshot:
  - `vendor/agent-canon/`
- root 側の shared runtime surface:
  - `documents/SHARED_RUNTIME_SURFACES.md` に載っている symlink view または synced copy
- root 側の template entrypoint:
  - `README.md`
  - `QUICK_START.md`
  - `documents/README.md`
  - `documents/WORKFLOW_GUIDE.md`
  - `scripts/README.md`
  - `notes/README.md`

## 所有境界

- `vendor/agent-canon/`:
  - workflow canon
  - skill canon
  - subagent 定義
  - shared notes template
  - shared CI / review / runtime helper
  - subtree / PR / shared surface ownership 文書
- root 側:
  - template 利用者向けの入口
  - implementation 本体
  - environment / server / template bootstrap
  - repo-local experiment topic
  - repo-local notes

## 編集ルール

- shared canon を直すときは `vendor/agent-canon/` 側を編集します。
- root 側の symlink view や synced copy を直接編集しません。
- shared surface を増減したら、同じ pass で link spec と ownership 文書を更新します。
- root 側の入口文書を変える場合でも、shared canon の説明は `agent-canon` 側の正本に寄せます。

## 同期ルール

template repo 側では次を使います。

```bash
bash scripts/sync_agent_canon.sh status
bash scripts/sync_agent_canon.sh link-root
bash scripts/sync_agent_canon.sh check
bash scripts/sync_agent_canon.sh pull
bash scripts/sync_agent_canon.sh push
```

- `link-root`:
  - root の symlink view と synced copy を vendor 正本から再構成する
- `check`:
  - root surface と vendor 正本の drift を検出する
- `pull`:
  - upstream `agent-canon` の更新を template 側 snapshot へ取り込む
- `push`:
  - template 側で育った shared canon を upstream `agent-canon` へ戻す

## PR ルール

- shared canon 変更は dedicated branch と dedicated PR に分けます。
- shared canon 変更は repo-local implementation change と同じ PR に混ぜません。
- PR 前の機械 gate は `make agent-canon-pr-check` を使います。
- merge 後は `bash scripts/sync_agent_canon.sh push` で upstream `agent-canon` を更新します。

## 完了条件

次をすべて満たしたときだけ subtree 変更を完了扱いにします。

- `bash scripts/sync_agent_canon.sh check` が pass
- `make agent-canon-pr-check` が pass
- root 側の shared surface が構成どおりに再同期されている
- template 側の PR merge 後に upstream `agent-canon` push を実行したか、未実行理由が明示されている

## 参照先

- `README.md`
- `documents/WORKFLOW_GUIDE.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-pr-workflow.md`
- `scripts/shared/error_handler.py`
- `scripts/validation/triplet_validator.py`
- `scripts/tools/audit_and_fix_links.py`
- `scripts/tools/check_markdown_lint.py`
- `scripts/tools/check_markdown_math.py`
- `scripts/tools/mirror_skill_shims.py`
- `scripts/agent_tools/bootstrap_agent_run.py`
- `scripts/agent_tools/smoke_test_research_perspective_pack.py`
- `scripts/agent_tools/validate_role_write_scope.py`
- `scripts/agent_tools/agent_team.py`
- `scripts/agent_tools/worktree_scope_lint.py`
- `scripts/agent_tools/worktree_start.py`
- `scripts/setup_worktree.sh`
- `scripts/worktree_start.sh`
- `scripts/tools/check_worktree_scopes.sh`
- `scripts/tools/create_worktree.sh`

## 5. wrapper の考え方

root 側は次のような薄い wrapper と symlink view にします。

- `AGENTS.md`
  - `vendor/agent-canon/ROOT_AGENTS.md` への symlink view
- `.codex/config.toml`
  - `vendor/agent-canon/.codex/config.toml` への symlink view
- `CLAUDE.md`
  - `vendor/agent-canon/CLAUDE.md` への symlink view
- `.github/AGENTS.md`
  - `vendor/agent-canon/.github/AGENTS.md` への symlink view
- `.github/copilot-instructions.md`
  - `vendor/agent-canon/.github/copilot-instructions.md` への symlink view
- `.codex/README.md`
  - `vendor/agent-canon/.codex/README.md` への symlink view
- `documents/BRANCH_SCOPE.md`
  - `vendor/agent-canon/documents/BRANCH_SCOPE.md` への symlink view
- `documents/agent-canon-subtree-migration.md`
  - `vendor/agent-canon/documents/agent-canon-subtree-migration.md` への symlink view
- `documents/AGENTS_COORDINATION.md`
  - `vendor/agent-canon/documents/AGENTS_COORDINATION.md` への symlink view
- `documents/academic-writing-workflow.md`
  - `vendor/agent-canon/documents/academic-writing-workflow.md` への symlink view
- `documents/REVIEW_PROCESS.md`
  - `vendor/agent-canon/documents/REVIEW_PROCESS.md` への symlink view
- `documents/SHARED_RUNTIME_SURFACES.md`
  - `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md` への symlink view
- `documents/WORKFLOW_GUIDE.md`
  - `vendor/agent-canon/documents/WORKFLOW_GUIDE.md` への symlink view
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
  - `vendor/agent-canon/documents/SKILL_IMPLEMENTATION_GUIDE.md` への symlink view
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
  - `vendor/agent-canon/documents/WORKTREE_SCOPE_TEMPLATE.md` への symlink view
- `documents/coding-conventions-experiments.md`
  - `vendor/agent-canon/documents/coding-conventions-experiments.md` への symlink view
- `documents/experiment-critical-review.md`
  - `vendor/agent-canon/documents/experiment-critical-review.md` への symlink view
- `documents/experiment-registry.md`
  - `vendor/agent-canon/documents/experiment-registry.md` への symlink view
- `documents/experiment-report-style.md`
  - `vendor/agent-canon/documents/experiment-report-style.md` への symlink view
- `documents/experiment-workflow.md`
  - `vendor/agent-canon/documents/experiment-workflow.md` への symlink view
- `documents/experiment_runner.md`
  - `vendor/agent-canon/documents/experiment_runner.md` への symlink view
- `documents/implementation-waterfall-workflow.md`
  - `vendor/agent-canon/documents/implementation-waterfall-workflow.md` への symlink view
- `documents/long-form-writing-workflow.md`
  - `vendor/agent-canon/documents/long-form-writing-workflow.md` への symlink view
- `documents/research-workflow.md`
  - `vendor/agent-canon/documents/research-workflow.md` への symlink view
- `documents/workflow-references.md`
  - `vendor/agent-canon/documents/workflow-references.md` への symlink view
- `documents/worktree-lifecycle.md`
  - `vendor/agent-canon/documents/worktree-lifecycle.md` への symlink view
- `documents/conventions/python/20_benchmark_policy.md`
  - `vendor/agent-canon/documents/conventions/python/20_benchmark_policy.md` への symlink view
- `documents/conventions/python/30_experiment_directory_structure.md`
  - `vendor/agent-canon/documents/conventions/python/30_experiment_directory_structure.md` への symlink view
- `experiments/README.md`
  - `vendor/agent-canon/experiments/README.md` への symlink view
- `experiments/_template/`
  - `vendor/agent-canon/experiments/_template/` への symlink view
- `experiments/report/README.md`
  - `vendor/agent-canon/experiments/report/README.md` への symlink view
- `notes/experiments/README.md`
  - `vendor/agent-canon/notes/experiments/README.md` への symlink view
- `notes/experiments/REPORT_TEMPLATE.md`
  - `vendor/agent-canon/notes/experiments/REPORT_TEMPLATE.md` への symlink view
- `notes/experiments/results/README.md`
  - `vendor/agent-canon/notes/experiments/results/README.md` への symlink view
- `notes/knowledge/benchmark_vs_experiment.md`
  - `vendor/agent-canon/notes/knowledge/benchmark_vs_experiment.md` への symlink view
- `notes/knowledge/experiment_directory_planning.md`
  - `vendor/agent-canon/notes/knowledge/experiment_directory_planning.md` への symlink view
- `notes/knowledge/experiment_operations.md`
  - `vendor/agent-canon/notes/knowledge/experiment_operations.md` への symlink view
- `notes/worktrees/README.md`
  - `vendor/agent-canon/notes/worktrees/README.md` への symlink view
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
  - `vendor/agent-canon/notes/worktrees/WORKTREE_LOG_TEMPLATE.md` への symlink view
- `notes/themes/from_another_agent.md`
  - `vendor/agent-canon/notes/themes/from_another_agent.md` への symlink view
- `agents/`
  - `vendor/agent-canon/agents/` への symlink view
- `.agents/`
  - `vendor/agent-canon/.agents/` への symlink view
- `.claude/`
  - `vendor/agent-canon/.claude/` への symlink view
- `tests/agent_tools/__init__.py`
  - `vendor/agent-canon/tests/agent_tools/__init__.py` への symlink view
- `tests/agent_tools/test_check_agent_runtime_alignment.py`
  - `vendor/agent-canon/tests/agent_tools/test_check_agent_runtime_alignment.py` への symlink view
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
  - `vendor/agent-canon/tests/agent_tools/test_smoke_test_research_perspective_pack.py` への symlink view
- `tests/tools/test_mirror_skill_shims.py`
  - `vendor/agent-canon/tests/tools/test_mirror_skill_shims.py` への symlink view
- `tests/tools/test_run_managed_experiment.py`
  - `vendor/agent-canon/tests/tools/test_run_managed_experiment.py` への symlink view
- `scripts/agent_tools/`
  - `vendor/agent-canon/scripts/agent_tools/` への symlink view
- `scripts/check_convention_consistency.py`
  - `vendor/agent-canon/scripts/check_convention_consistency.py` への symlink view
- `scripts/check_doc_test_triplet.py`
  - `vendor/agent-canon/scripts/check_doc_test_triplet.py` への symlink view
- `scripts/docker_dependency_validator.py`
  - `vendor/agent-canon/scripts/docker_dependency_validator.py` への symlink view
- `scripts/requirement_sync_validator.py`
  - `vendor/agent-canon/scripts/requirement_sync_validator.py` への symlink view
- `scripts/run_comprehensive_review.sh`
  - `vendor/agent-canon/scripts/run_comprehensive_review.sh` への symlink view
- `scripts/ci/PRE_REVIEW_GUIDE.md`
  - `vendor/agent-canon/scripts/ci/PRE_REVIEW_GUIDE.md` への symlink view
- `scripts/ci/check_docker_build.sh`
  - `vendor/agent-canon/scripts/ci/check_docker_build.sh` への symlink view
- `scripts/ci/check_experiment_registry.py`
  - `vendor/agent-canon/scripts/ci/check_experiment_registry.py` への symlink view
- `scripts/ci/check_server_readiness.py`
  - `vendor/agent-canon/scripts/ci/check_server_readiness.py` への symlink view
- `scripts/ci/container_runtime.py`
  - `vendor/agent-canon/scripts/ci/container_runtime.py` への symlink view
- `scripts/ci/pre_review.sh`
  - `vendor/agent-canon/scripts/ci/pre_review.sh` への symlink view
- `scripts/ci/run_all_checks.sh`
  - `vendor/agent-canon/scripts/ci/run_all_checks.sh` への symlink view
- `scripts/ci/run_codex_in_repo_container.py`
  - `vendor/agent-canon/scripts/ci/run_codex_in_repo_container.py` への symlink view
- `scripts/ci/run_container_pack.py`
  - `vendor/agent-canon/scripts/ci/run_container_pack.py` への symlink view
- `scripts/ci/run_docs_checks.sh`
  - `vendor/agent-canon/scripts/ci/run_docs_checks.sh` への symlink view
- `scripts/ci/run_in_repo_container.py`
  - `vendor/agent-canon/scripts/ci/run_in_repo_container.py` への symlink view
- `scripts/ci/run_python_in_dockerfile.py`
  - `vendor/agent-canon/scripts/ci/run_python_in_dockerfile.py` への symlink view
- `scripts/experiments/create_experiment_topic.py`
  - `vendor/agent-canon/scripts/experiments/create_experiment_topic.py` への symlink view
- `scripts/experiments/registry_lib.py`
  - `vendor/agent-canon/scripts/experiments/registry_lib.py` への symlink view
- `scripts/experiments/run_managed_experiment.py`
  - `vendor/agent-canon/scripts/experiments/run_managed_experiment.py` への symlink view
- `scripts/experiments/sync_experiment_registry_context.py`
  - `vendor/agent-canon/scripts/experiments/sync_experiment_registry_context.py` への symlink view
- `scripts/setup_worktree.sh`
  - `vendor/agent-canon/scripts/setup_worktree.sh` への symlink view
- `scripts/shared/error_handler.py`
  - `vendor/agent-canon/scripts/shared/error_handler.py` への symlink view
- `scripts/sync_agent_canon.sh`
  - `vendor/agent-canon/scripts/sync_agent_canon.sh` への symlink view
- `scripts/tools/audit_and_fix_links.py`
  - `vendor/agent-canon/scripts/tools/audit_and_fix_links.py` への symlink view
- `scripts/tools/check_markdown_lint.py`
  - `vendor/agent-canon/scripts/tools/check_markdown_lint.py` への symlink view
- `scripts/tools/check_markdown_math.py`
  - `vendor/agent-canon/scripts/tools/check_markdown_math.py` への symlink view
- `scripts/worktree_start.sh`
  - `vendor/agent-canon/scripts/worktree_start.sh` への symlink view
- `scripts/tools/check_worktree_scopes.sh`
  - `vendor/agent-canon/scripts/tools/check_worktree_scopes.sh` への symlink view
- `scripts/tools/create_worktree.sh`
  - `vendor/agent-canon/scripts/tools/create_worktree.sh` への symlink view
- `scripts/tools/mirror_skill_shims.py`
  - `vendor/agent-canon/scripts/tools/mirror_skill_shims.py` への symlink view
- `scripts/validation/triplet_validator.py`
  - `vendor/agent-canon/scripts/validation/triplet_validator.py` への symlink view
- `.github/workflows/agent-coordination.yml`
  - `vendor/agent-canon/.github/workflows/agent-coordination.yml` から root へ同期する copy surface

重要:
- subtree 配下にも `AGENTS.md` は置けますが、通常は canon 開発 subtree 用 override としてのみ使います
- root runtime の正面入口は root に固定します
- shared canon の source of truth は root 側ではなく `vendor/agent-canon/` です

## 6. worktree と subtree の関係

- template / 派生 repo で worktree を切ると、その branch / commit に入っている `vendor/agent-canon/` snapshot がそのまま見えます
- upstream `agent-canon` の最新が自動で流入するわけではありません
- shared canon の更新は、明示的に subtree pull した branch にだけ反映されます

つまり:
- worktree は snapshot を使う仕組み
- shared canon 更新は subtree sync で行う仕組み

## 7. 標準運用

### 7.1 root symlink surface を修復

```bash
bash scripts/sync_agent_canon.sh link-root
bash scripts/sync_agent_canon.sh check
```

### 7.2 互換 alias

既存の `snapshot` command は後方互換のため `link-root` の alias として残します。

```bash
bash scripts/sync_agent_canon.sh snapshot
```

### 7.3 初回取り込み

```bash
bash scripts/sync_agent_canon.sh add git@github.com:<org>/agent-canon.git
```

### 7.4 upstream から更新取得

```bash
bash scripts/sync_agent_canon.sh pull
```

### 7.5 template / 派生 repo 側の shared canon 変更を upstream へ戻す

```bash
bash scripts/sync_agent_canon.sh push
```

### 7.6 現在の設定確認

```bash
bash scripts/sync_agent_canon.sh status
```

## 8. 移行フェーズ

### Phase 0. template 側の基盤整備

この template で完了していること:
- migration 正本を作る
- `vendor/agent-canon/` の committed snapshot を置く
- subtree sync script を追加する
- root `AGENTS.md` を shared runtime surface に寄せる
- root の shared docs / scripts / discovery surface を symlink view に寄せる
- root `.codex/config.toml` も shared default に寄せる

### Phase 1. upstream `agent-canon` repo を作る

残タスク:
- `vendor/agent-canon/` の履歴を upstream repo として切り出す
- template 側に subtree remote を設定する
- `subtree add / pull / push` の正規運用へ移る

exit 条件:
- upstream repo 単体で shared canon を保持できる
- template / 派生 repo 側に subtree add / split できる snapshot history を持てる

### Phase 2. template bootstrap command を追加する

候補:
- `scripts/bootstrap_derived_repo.py`
- `scripts/new_product.sh`

役割:
- template clone 後の repo 名差し替え
- subtree remote 設定
- optional pack 選択

## 9. リスクと抑止策

### root entrypoint が壊れる

抑止:
- root `AGENTS.md` と root `.codex/` の discovery path は最後まで消さない
- wrapper は instance-local 情報だけに絞る

### shared canon と instance-local 文書が混ざる

抑止:
- `agent-canon` へ移す範囲を phase で分ける
- Docker、server、experiment の文書は root 側に残す

### template / 派生 repo 側で直した canon を upstream へ戻せない

抑止:
- `vendor/agent-canon/` の変更は専用 commit に分ける
- `git subtree push --prefix=vendor/agent-canon` を標準運用にする
- 外部 repo をまだ作っていない段階では `snapshot` で vendor tree を更新し、repo 作成時に `git subtree split --prefix=vendor/agent-canon` から初期 history を切り出す

### worktree ごとに shared canon がばらつく

抑止:
- それは意図した snapshot 運用とみなす
- どの branch がどの subtree commit を含むかを commit history で追えるようにする

## 10. 完了条件

- upstream `agent-canon` repo が存在する
- template repo が `vendor/agent-canon/` subtree snapshot を持つ
- root `AGENTS.md` と root `.codex/` は root discovery path として機能する
- template / 派生 repo で worktree を切ったとき、その時点の shared canon snapshot が `vendor/agent-canon/` として見える
- template / 派生 repo 側で直した shared canon を `git subtree push` で upstream へ戻せる
- upstream repo 作成前でも、`git clone <template>` 直後に `vendor/agent-canon/` snapshot が揃っている

## 11. 関連

- [README.md](/mnt/l/workspace/project_template/README.md)
- [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
- [WORKFLOW_GUIDE.md](/mnt/l/workspace/project_template/documents/WORKFLOW_GUIDE.md)
- [workflow-references.md](/mnt/l/workspace/project_template/documents/workflow-references.md)
- [README.md](/mnt/l/workspace/project_template/vendor/README.md)
- [sync_agent_canon.sh](/mnt/l/workspace/project_template/scripts/sync_agent_canon.sh)
