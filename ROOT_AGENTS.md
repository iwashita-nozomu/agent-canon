# Agent Instructions

This file is the template-root runtime entrypoint for Codex and GitHub Copilot.
The shared agent canon lives in `vendor/agent-canon/`, and the root discovery paths are runtime views into that snapshot.

## Read First

- `README.md`
- `documents/WORKFLOW_GUIDE.md`
- `agents/README.md`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `documents/AGENTS_COORDINATION.md`
- `docker/README.md`

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance live in `docker/`.
- Repo-wide durable rules live in `documents/`.

## Required Before Implementation

- 設計変更、実装、文書改訂、実験計画の前に、`documents/`、`notes/knowledge/`、`notes/guardrails/`、`notes/failures/`、`notes/themes/`、`notes/branches/`、`notes/worktrees/`、`notes/experiments/`、`references/` を topic keyword で探索します。
- 新しい code path、module、helper、test、script を足す前に、`python/`、`tests/`、`src/`、`include/`、`lib/`、`scripts/` を topic keyword で探索し、既存実装の再利用候補を確認します。
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を短く宣言します。
- skill を user-facing に明示する場合の既定表記は `$skill-name` です。

## Shared Canon

- Shared workflow, skills, subagents, docs, and support scripts are maintained in the vendored canon, not in this wrapper.
- role behavior, stage prohibitions, and review separation rules should live first in `.codex/agents/*.toml`; keep this file as a thin entrypoint
- Repo-changing tasks follow the staged flow in `agents/canonical/CODEX_WORKFLOW.md`: requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation.
- code-changing tasks add `test_designer` before implementation and fix nasty cases into tests in the same pass.
- Keep `plan_reviewer`, `detailed_design_reviewer`, and `document_flow_reviewer` as separate agent instances.
- Repo-changing task では run bundle と explicit stage activation を先に作ります。
- skill を user から指定するときは `$research-workflow` や `$paper-writing` のような `$skill-name` を優先します。
- Codex で planning を回すときは、parent session 側の plan-mode command を使います。official Codex CLI では `/plan` です。
- Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。
- 標準 bundle の入口は次です。

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

- `--task-id` を使うと、task catalog の default specialist と default review pack を自動で有効化します。

- Long README, workflow, guide, and migration docs should use `agents/skills/long-form-writing.md` and require subagent review before closeout.
- Academic papers, thesis chapters, scholarly notes, and symbol-dense claim-heavy documents should use `agents/skills/academic-writing.md` and require separate notation and logic reviewers before closeout.
- 投稿論文や thesis chapter の draft では `agents/skills/paper-writing.md` を優先し、citation / evidence reviewer も通します。
- tuning、比較改善、探索的改造を backlog 付きで継続反復する task では `agents/skills/adaptive-improvement-loop.md` を outer loop にします。
- worktree で作業する場合は `bash scripts/worktree_start.sh <branch> [worktree-path]` で kickoff し、継続ログは `python3 scripts/agent_tools/work_log.py --kind <kind> --message "<what changed>" --next "<next>"` で残します。
- file 構成変更を含む branch を `main` に戻すときは `documents/main-integration-workflow.md` に従い、integration worktree 上で `python3 scripts/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- closeout 前に `documents/notes-lifecycle.md` を見て、worktree log から `notes/knowledge/`、`notes/themes/`、`notes/failures/` への昇格先を決めます。
- user-facing completion report は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になるまで出してはいけません。
- If a shared surface drifts, repair it with `bash scripts/sync_agent_canon.sh link-root`.
- `link-root` restores both symlink views and root files that are intentionally synced as copies.
- If you need to change shared canon itself, treat `vendor/agent-canon/` as the source of truth.
- `.codex/config.toml` is the default shared Codex config; replace the symlink only when a repo-local override is intentional.

## Close-Out Prohibitions

- 会話だけを根拠に実装へ進めてはいけません。
- reuse sweep をせずに新しい file や module を増やしてはいけません。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務してはいけません。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略してはいけません。
- required review、validation、tracked change の commit / push を省略して完了扱いにしてはいけません。
- `verification.txt` が `status=pass` でない、または `closeout_gate.md` が `user_completion_report=unlocked` でない状態で user-facing 完了報告を出してはいけません。

## Validation

- `make agent-checks`
- `make ci-quick`
- `make docs-check`
- `python3 -m pytest tests/ -q --tb=short`
