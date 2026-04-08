# ユーザー向けワークフローガイド

この文書は、この template repo の workflow canon 入口です。
workflow 系の正本は shared agent canon に寄せ、template root と派生 repo root では同じ path を symlink view として使います。

## Workflow Canon

- 実装変更:
  - `documents/implementation-waterfall-workflow.md`
- 長文作成:
  - `documents/long-form-writing-workflow.md`
- 学術文章作成:
  - `documents/academic-writing-workflow.md`
- 実験 run:
  - `documents/experiment-workflow.md`
- research-driven な改善:
  - `documents/research-workflow.md`
- worktree lifecycle:
  - `documents/worktree-lifecycle.md`
- workflow 根拠:
  - `documents/workflow-references.md`

workflow の具体的な role routing は `agents/TASK_WORKFLOWS.md` と `agents/canonical/CODEX_WORKFLOW.md` を使います。

## まず決めること

作業を始める前に、次の 3 点を切ります。

1. 実装変更か、文書変更か、実験変更か、環境変更か
1. 正本を更新する task か、補助 note で足りる task か
1. `make ci-quick` で足りるか、`make ci` や Docker check まで必要か

## やりたいこと別の入口

| やりたいこと | 最初に読む | 主に触る場所 | 最低限の確認 |
| --- | --- | --- | --- |
| repo の全体像を知りたい | `README.md`, `QUICK_START.md` | `documents/`, `scripts/`, `docker/` | `make ci-quick` |
| Python 実装を直したい | `documents/coding-conventions-python.md`, `documents/implementation-waterfall-workflow.md` | `python/`, `tests/` | `make ci-quick` |
| 長い README や guide を書きたい | `documents/long-form-writing-workflow.md` | `documents/`, `notes/`, `agents/` | `make docs-check` |
| 論文や thesis chapter を書きたい | `documents/academic-writing-workflow.md` | `documents/`, `notes/`, `agents/`, `references/` | `make docs-check` |
| 文書だけ更新したい | `documents/README.md` | `documents/`, `notes/` | `make docs-check` |
| Docker / 依存を更新したい | `docker/README.md` | `docker/`, `scripts/ci/` | `make docker-build-check` |
| main server host の readiness を見たい | `documents/server-host-contract.md` | `documents/templates/`, `scripts/ci/` | `python3 scripts/ci/check_server_readiness.py` |
| container で Python file を再現したい | `docker/README.md` | `docker/`, `scripts/ci/` | `python3 scripts/ci/run_python_in_dockerfile.py ... --print-only` |
| nested Codex を container 内で動かしたい | `docker/README.md` | `docker/`, `scripts/ci/`, `.state/` | `python3 scripts/ci/run_codex_in_repo_container.py --print-only` |
| 実験を進めたい | `documents/experiment-workflow.md` | `experiments/`, `experiments/registry.toml`, `notes/`, `scripts/experiments/` | report と result の対応確認 |
| research-driven な改善をしたい | `documents/research-workflow.md` | `documents/`, `experiments/`, `notes/` | review loop の完結 |
| agent を使いたい | `agents/README.md` | `agents/`, `reports/agents/` | `make agent-checks` |
| shared agent canon を subtree で同期したい | `documents/agent-canon-subtree-migration.md` | `vendor/`, `scripts/sync_agent_canon.sh` | `make agent-checks` |

## 標準フロー

### 1. 日常の実装変更

1. 変更対象を決めます。
1. `documents/implementation-waterfall-workflow.md` に従って、requirements、plan、detailed design、document flow review を先に固定します。
1. 変更前に baseline を確認します。
1. 実装と文書を同じ変更でそろえます。
1. `make ci-quick` で早い確認をします。
1. 仕上げ前に `make ci` まで通します。

```bash
git status --short
make ci-quick
python3 -m pyright
python3 -m pytest tests/ -q --tb=short
make ci
```

### 2. 文書だけを更新するとき

- repo-wide のルールや手順:
  - `documents/`
- cross-run の補助知見:
  - `notes/`
- agent 間で共有する運用:
  - `agents/`

README、workflow、guide、migration 文書のような長文では、先に `documents/long-form-writing-workflow.md` を読みます。
長文では `document_flow_reviewer` と別 reviewer の両方を前提にします。
学術文章では、さらに `documents/academic-writing-workflow.md` を読み、`notation_definition_reviewer` と `logic_gap_reviewer` も前提にします。

```bash
make docs-check
python3 scripts/tools/check_markdown_lint.py documents
python3 scripts/tools/audit_and_fix_links.py --check documents
```

### 3. Docker / 環境を更新するとき

Docker / tool / runtime に触る task では、少なくとも次を同じ変更で扱います。

- `docker/Dockerfile`
- `docker/requirements.txt`
- `docker/README.md`
- 必要なら `README.md`、`QUICK_START.md`、`documents/coding-conventions-project.md`

```bash
python3 scripts/docker_dependency_validator.py
make docker-build-check
python3 scripts/ci/run_container_pack.py --pack docker/packs/default.toml --print-only
```

host Docker socket も必要なら次です。

```bash
make docker-build-check-host-docker
python3 scripts/ci/run_container_pack.py --pack docker/packs/default-host-docker.toml --print-only
```

### 4. Worktree を例外運用するとき

新しい worktree を切るか、既存 worktree を再開するときは `worktree-start` を使います。

```bash
bash scripts/worktree_start.sh work/my-topic-YYYYMMDD
python3 scripts/agent_tools/worktree_scope_lint.py --current
```

scope drift や cleanup readiness を見たいときは `worktree-health` を使います。

### 5. shared agent canon を同期するとき

shared agent canon を別 repo に切り出したあとは、template / 派生 repo 側では subtree snapshot を同期します。

```bash
bash scripts/sync_agent_canon.sh link-root
bash scripts/sync_agent_canon.sh check
bash scripts/sync_agent_canon.sh status
bash scripts/sync_agent_canon.sh pull
make agent-checks
```

ownership と surface 種別は `documents/SHARED_RUNTIME_SURFACES.md` を参照します。

template / 派生 repo 側で shared canon を直した変更を upstream へ戻すときは、`vendor/agent-canon/` 配下だけを専用 commit に分けてから `push` を使います。

### 6. closeout

変更を閉じる前に、次を揃えます。

1. 必要な validation を実行する
1. action log や note を current state に更新する
1. commit する
1. `origin` へ push する
1. そのあとで完了報告する

```bash
git status --short
make ci-quick
git add <files>
git commit -m "<type>: <summary>"
bash scripts/push_origin.sh
```
