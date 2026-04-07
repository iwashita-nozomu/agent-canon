# agent-canon subtree 移行計画

この文書は、shared agent canon を別 repo `agent-canon` として切り出し、product template 側へ `git subtree` で取り込むための正本です。
目的は、`git clone <template>` だけで新しい product を始められることを維持しながら、agent 運用の正本を upstream repo へ分離することです。
この template ではすでに `vendor/agent-canon/` に committed snapshot を持ち、shared surface の大半を root symlink view に寄せています。
将来的には experiment-oriented な agent set として `agent-canon` 単体で配布できるよう、実験運用の規約、review guide、registry tool、topic scaffold も shared canon 側へ寄せます。

## 1. この構成を選ぶ理由

- `git clone <template>` だけで product を開始したい
- product 側の worktree に、その時点の agent canon snapshot を閉じ込めたい
- product 側で直した shared canon を、後から upstream `agent-canon` repo へ戻したい
- Codex の runtime discovery は root `AGENTS.md` と root `.codex/` を前提にしたい
- sibling repo 参照や手動コピーには依存したくない

この条件では、`submodule` より `subtree` の方が扱いやすく、repo 外参照より再現性が高いです。

## 2. 非目標

- `agent-canon` を repo 外の sibling directory として自動 discovery させること
- root `AGENTS.md` と root `.codex/` を無くすこと
- branch を product variant ごとに長期運用すること
- 一回の変更で template から agent 関連を全部剥がすこと

## 3. 目標構成

```text
product-repo/
├─ AGENTS.md
├─ CLAUDE.md
├─ .github/
│  ├─ AGENTS.md
│  ├─ copilot-instructions.md
│  └─ workflows/
│     └─ agent-coordination.yml
├─ .codex/
│  ├─ config.toml
│  └─ README.md
├─ vendor/
│  └─ agent-canon/
│     ├─ agents/
│     ├─ .agents/
│     ├─ .claude/
│     ├─ .codex/agents/
│     └─ shared agent-facing docs
├─ python/
│  └─ tests/
│     ├─ agent_tools/
│     └─ tools/
│        └─ test_mirror_skill_shims.py
├─ docker/
├─ documents/
│  ├─ BRANCH_SCOPE.md
│  ├─ AGENTS_COORDINATION.md
│  ├─ REVIEW_PROCESS.md
│  ├─ SKILL_IMPLEMENTATION_GUIDE.md
│  ├─ WORKTREE_SCOPE_TEMPLATE.md
│  ├─ implementation-waterfall-workflow.md
│  ├─ workflow-references.md
│  └─ worktree-lifecycle.md
├─ notes/
│  └─ themes/
│     └─ from_another_agent.md
└─ scripts/
   ├─ agent_tools/
   ├─ setup_worktree.sh
   ├─ worktree_start.sh
   └─ tools/
      ├─ check_worktree_scopes.sh
      ├─ create_worktree.sh
      └─ mirror_skill_shims.py
```

原則:
- root `AGENTS.md` と root `.codex/` は product repo の runtime entrypoint として残します
- shared canon の実体は `vendor/agent-canon/` の subtree snapshot に寄せます
- shared canon を root から使う surface は symlink view に寄せます
- product 固有の README、Docker、CI、実装、server 運用文書は root 側に残します

## 4. 所有境界

### 4.1 `agent-canon` へ移すもの

shared canon の正本として扱う対象:
- `agents/`
- `.agents/`
- `.claude/`
- `ROOT_AGENTS.md`
- `CLAUDE.md`
- `.github/AGENTS.md`
- `.github/copilot-instructions.md`
- `.github/workflows/agent-coordination.yml`
- `.codex/config.toml`
- `.codex/README.md`
- `.codex/agents/`
- `documents/agent-canon-subtree-migration.md`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/WORKFLOW_GUIDE.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/coding-conventions-experiments.md`
- `documents/experiment-critical-review.md`
- `documents/experiment-registry.md`
- `documents/experiment-report-style.md`
- `documents/experiment-workflow.md`
- `documents/experiment_runner.md`
- `documents/implementation-waterfall-workflow.md`
- `documents/research-workflow.md`
- `documents/workflow-references.md`
- `documents/worktree-lifecycle.md`
- `documents/conventions/python/20_benchmark_policy.md`
- `documents/conventions/python/30_experiment_directory_structure.md`
- `experiments/README.md`
- `experiments/_template/`
- `experiments/report/README.md`
- `notes/experiments/README.md`
- `notes/experiments/REPORT_TEMPLATE.md`
- `notes/experiments/results/README.md`
- `notes/knowledge/benchmark_vs_experiment.md`
- `notes/knowledge/experiment_directory_planning.md`
- `notes/knowledge/experiment_operations.md`
- `notes/themes/from_another_agent.md`
- `notes/worktrees/README.md`
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `tests/agent_tools/__init__.py`
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
- `tests/tools/test_mirror_skill_shims.py`
- `tests/tools/test_run_managed_experiment.py`
- `scripts/agent_tools/`
- `scripts/ci/check_experiment_registry.py`
- `scripts/experiments/`
- `scripts/setup_worktree.sh`
- `scripts/sync_agent_canon.sh`
- `scripts/worktree_start.sh`
- `scripts/tools/check_worktree_scopes.sh`
- `scripts/tools/create_worktree.sh`
- `scripts/tools/mirror_skill_shims.py`
- `vendor/agent-canon/AGENTS.md`
- `vendor/agent-canon/README.md`

### 4.2 product template に残すもの

- `README.md`
- `docker/`
- `scripts/`
- product implementation と shared canon 以外の `python/`
- `experiments/`
- shared canon 以外の `notes/`
- `documents/` のうち product / environment / server / experiment に閉じるもの

補足:
- `docker` 以外の全部を `agent-canon` へ移すわけではありません
- implementation、experiment、server operation、generic project bootstrap は product template 側に残します
- product 側の `experiments/` では `registry.toml`、topic 固有ディレクトリ、run artifact だけを正本に残し、shared scaffold と運用 guide は `agent-canon` へ寄せます
- root の `AGENTS.md`、`agents/`、`.agents/`、`.claude/`、`CLAUDE.md`、`.github/AGENTS.md`、`.github/copilot-instructions.md`、`.codex/config.toml`、`.codex/agents`、`.codex/README.md`、`documents/agent-canon-subtree-migration.md`、`documents/BRANCH_SCOPE.md`、`documents/AGENTS_COORDINATION.md`、`documents/REVIEW_PROCESS.md`、`documents/SHARED_RUNTIME_SURFACES.md`、`documents/SKILL_IMPLEMENTATION_GUIDE.md`、`documents/WORKFLOW_GUIDE.md`、`documents/WORKTREE_SCOPE_TEMPLATE.md`、`documents/coding-conventions-experiments.md`、`documents/experiment-critical-review.md`、`documents/experiment-registry.md`、`documents/experiment-report-style.md`、`documents/experiment-workflow.md`、`documents/experiment_runner.md`、`documents/implementation-waterfall-workflow.md`、`documents/research-workflow.md`、`documents/workflow-references.md`、`documents/worktree-lifecycle.md`、`documents/conventions/python/20_benchmark_policy.md`、`documents/conventions/python/30_experiment_directory_structure.md`、`experiments/README.md`、`experiments/_template/`、`experiments/report/README.md`、`notes/experiments/README.md`、`notes/experiments/REPORT_TEMPLATE.md`、`notes/experiments/results/README.md`、`notes/knowledge/benchmark_vs_experiment.md`、`notes/knowledge/experiment_directory_planning.md`、`notes/knowledge/experiment_operations.md`、`notes/themes/from_another_agent.md`、`notes/worktrees/README.md`、`notes/worktrees/WORKTREE_LOG_TEMPLATE.md`、`tests/agent_tools/__init__.py`、`tests/agent_tools/test_smoke_test_research_perspective_pack.py`、`tests/tools/test_mirror_skill_shims.py`、`tests/tools/test_run_managed_experiment.py`、`scripts/agent_tools/`、`scripts/ci/check_experiment_registry.py`、`scripts/experiments/` 配下の helper、`scripts/setup_worktree.sh`、`scripts/sync_agent_canon.sh`、`scripts/worktree_start.sh`、`scripts/tools/check_worktree_scopes.sh`、`scripts/tools/create_worktree.sh`、`scripts/tools/mirror_skill_shims.py` は shared canon への symlink view にします
- `.github/workflows/agent-coordination.yml` は shared canon 正本から root へ同期する copy surface にします

### 4.3 vendor-aware 化が必要な support surface

shared canon を vendor 正本へ寄せても、root path はそのまま使えるようにします。
この template では次を root symlink view にしたので、呼び出し側の path は変えずに済みます。

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
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
  - `vendor/agent-canon/tests/agent_tools/test_smoke_test_research_perspective_pack.py` への symlink view
- `tests/tools/test_mirror_skill_shims.py`
  - `vendor/agent-canon/tests/tools/test_mirror_skill_shims.py` への symlink view
- `tests/tools/test_run_managed_experiment.py`
  - `vendor/agent-canon/tests/tools/test_run_managed_experiment.py` への symlink view
- `scripts/agent_tools/`
  - `vendor/agent-canon/scripts/agent_tools/` への symlink view
- `scripts/ci/check_experiment_registry.py`
  - `vendor/agent-canon/scripts/ci/check_experiment_registry.py` への symlink view
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
- `scripts/sync_agent_canon.sh`
  - `vendor/agent-canon/scripts/sync_agent_canon.sh` への symlink view
- `scripts/worktree_start.sh`
  - `vendor/agent-canon/scripts/worktree_start.sh` への symlink view
- `scripts/tools/check_worktree_scopes.sh`
  - `vendor/agent-canon/scripts/tools/check_worktree_scopes.sh` への symlink view
- `scripts/tools/create_worktree.sh`
  - `vendor/agent-canon/scripts/tools/create_worktree.sh` への symlink view
- `scripts/tools/mirror_skill_shims.py`
  - `vendor/agent-canon/scripts/tools/mirror_skill_shims.py` への symlink view
- `.github/workflows/agent-coordination.yml`
  - `vendor/agent-canon/.github/workflows/agent-coordination.yml` から root へ同期する copy surface

重要:
- subtree 配下にも `AGENTS.md` は置けますが、通常は canon 開発 subtree 用 override としてのみ使います
- product runtime の正面入口は root に固定します
- shared canon の source of truth は root 側ではなく `vendor/agent-canon/` です

## 6. worktree と subtree の関係

- product repo で worktree を切ると、その branch / commit に入っている `vendor/agent-canon/` snapshot がそのまま見えます
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

### 7.5 product 側の shared canon 変更を upstream へ戻す

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
- product 側に subtree add / split できる snapshot history を持てる

### Phase 2. product bootstrap command を追加する

候補:
- `scripts/bootstrap_product.py`
- `scripts/new_product.sh`

役割:
- template clone 後の product 名差し替え
- subtree remote 設定
- optional pack 選択

## 9. リスクと抑止策

### root entrypoint が壊れる

抑止:
- root `AGENTS.md` と root `.codex/` の discovery path は最後まで消さない
- wrapper は product 固有情報だけに絞る

### shared canon と product 固有文書が混ざる

抑止:
- `agent-canon` へ移す範囲を phase で分ける
- Docker、server、experiment の文書は product 側に残す

### product 側で直した canon を upstream へ戻せない

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
- product で worktree を切ったとき、その時点の shared canon snapshot が `vendor/agent-canon/` として見える
- product 側で直した shared canon を `git subtree push` で upstream へ戻せる
- upstream repo 作成前でも、`git clone <template>` 直後に `vendor/agent-canon/` snapshot が揃っている

## 11. 関連

- [README.md](/mnt/l/workspace/project_template/README.md)
- [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
- [WORKFLOW_GUIDE.md](/mnt/l/workspace/project_template/documents/WORKFLOW_GUIDE.md)
- [workflow-references.md](/mnt/l/workspace/project_template/documents/workflow-references.md)
- [README.md](/mnt/l/workspace/project_template/vendor/README.md)
- [sync_agent_canon.sh](/mnt/l/workspace/project_template/scripts/sync_agent_canon.sh)
