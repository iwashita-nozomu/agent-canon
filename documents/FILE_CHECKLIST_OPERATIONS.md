<!--
@dependency-start
contract reference
responsibility Documents 作業別チェックリスト for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./github-first-module-and-devcontainer-policy.md environment ownership boundary
@dependency-end
-->

# 作業別チェックリスト

この文書は、テンプレで繰り返し出る典型作業の最小チェックリストをまとめます。
長い説明より、作業前後に確認すべき点を短く揃えるためのものです。

## この文書の読み方

- この文書は、作業種別ごとの最小チェック項目をまとめる運用 checklist です。
- 主な順路は、Worktree 開始、Python 実装変更、文書変更、Docker / 環境変更、
  closeout です。
- 作業開始時や closeout 前に、該当作業の確認漏れを減らすために読みます。
- 境界: 詳細な workflow 正本や validation matrix はリンク先の runtime/canon
  文書が所有します。

## 1. Worktree 開始

前提:

- `main` が `origin` と同期している
- 作業 topic が短く切れている

手順:

```bash
git switch -c work/<topic>-YYYYMMDD
python3 tools/agent_tools/worktree_scope_lint.py --current
git status --short --branch
git worktree list --porcelain
```

確認:

- stale `WORKTREE_SCOPE.md` を current task の scope authority として扱っていない
- action log path が concrete になっている
- `notes/guardrails/README.md` と `notes/failures/README.md` を見ている
- kickoff 後の次の 1 手が action log に残っている

## 2. Python 実装変更

前提:

- 触る module と test 範囲が決まっている

手順:

```bash
make ci-quick
python3 -m pyright
python3 -m pytest tests/ -q --tb=short
python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501
```

確認:

- 実装変更に対応する文書更新がある
- 失敗した test を放置していない
- import / type / docstring の警告を説明できる

## 3. 文書変更

手順:

```bash
tools/bin/agent-canon docs check <changed-file>.md
```

確認:

- `documents/` と `notes/` の置き分けが合っている
- hub 文書から辿れる
- stale command や stale path を残していない

## 4. Docker / 環境変更

手順:

```bash
bash tools/docker_dependency_validator.sh
python3 tools/ci/container_config.py
make docker-build-check
python3 tools/ci/run_container_pack.py --pack docker/packs/default.toml --print-only
```

必要なら:

```bash
make docker-build-check-host-docker
python3 tools/ci/run_codex_in_repo_container.py --profile host-docker --print-only
```

確認:

- repo-local `docker/Dockerfile`、`docker/requirements.txt`、AgentCanon-owned `.devcontainer/` の責務境界が同期している
- `docker/README.md`、`README.md`、`QUICK_START.md` が更新されている
- `agents/templates/environment_change_proposal.md` に proposal が残っている

## 5. closeout

手順:

```bash
git status --short
make ci-quick
git add <files>
git commit -m "<type>: <summary>"
python3 tools/agent_tools/github_publish.py push \
  --user-task "<current user task>" \
  --repo <owner/name>
```

確認:

- push 前に dirty worktree を残していない
- push は `github_publish.py` の verified remote route で実行している
- commit / push 済みの状態で完了報告する
- carry-over note や action log が current state に追随している
