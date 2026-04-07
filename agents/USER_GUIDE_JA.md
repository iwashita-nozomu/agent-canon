# エージェント利用ガイド

## どこから読むか

1. [agents/README.md](/mnt/l/workspace/project_template/agents/README.md)
1. [agents/canonical/README.md](/mnt/l/workspace/project_template/agents/canonical/README.md)
1. [agents/TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
1. [agents/skills/README.md](/mnt/l/workspace/project_template/agents/skills/README.md)

## 入口の使い分け

- Codex / Copilot agent mode:
  - [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
- Claude Code:
  - [CLAUDE.md](/mnt/l/workspace/project_template/CLAUDE.md)
- GitHub Copilot custom instructions:
  - [.github/copilot-instructions.md](/mnt/l/workspace/project_template/.github/copilot-instructions.md)

## skill の使い方

- 共通 skill の正本は `.agents/skills/` にあります。
- Claude では `.claude/skills/` の generated mirror を使います。正本は `.agents/skills/` です。
- どの skill を使うか迷う場合は、まず `repo-onboarding` か `agent-orchestration` を見ます。
- Codex で毎回同じ手順を踏みたい場合は `codex-task-workflow` を見ます。
- Python 差分では `python-review` を既定で使います。
- 局所 diff を findings-first で見るときは `code-review` か `change-review` を使います。
- Markdown / report 差分では `md-style-check` と必要なら `report-review` を使います。
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を使います。
- 文書の説明不足を拾うときは `docs-completeness-review` を使います。
- 文献調査や関連研究整理では `literature-survey` を使います。
- 研究系 task では `research-workflow` を外側の loop に使います。
- 実験結果を見ながら code change を継続反復する場合は `experiment-change-loop` を使います。
- 単一 run の review / rerun 分岐は `experiment-lifecycle` を使います。
- 研究設計や artifact 方針まで大きく触る場合は `research-perspective-review` を追加します。
- worktree を切った直後は `worktree-start` で scope と action log を固定し、drift や cleanup 判断は `worktree-health` を使います。
- repo 全体を横断して見るときは `project-review`、必要なら `comprehensive-review` と `project-health` を追加します。
- 文書の置き場で迷う場合は `artifact-placement` を見ます。
- 前回 agent run から引き継ぐ TODO や optional follow-up がある場合は `from_another_agent` を先に見ます。
- CLI 差分で迷う場合は `codex-cli`、`claude-code-cli`、`copilot-cli` を見ます。
- Docker、CI、dependency、repo-wide tool 導入案では `environment-maintenance` を使います。

## subagent の使い方

- Claude 専用 subagent は `.claude/agents/` にあります。
- Codex 用 subagent は `.codex/agents/` にあります。
- subagent は task 固有に使い、repo 全体の正本は `agents/` 側に置きます。
- specialist を立ち上げる前に `subagent-bootstrap` を見て、repo-changing task では run bundle を先に作ります。
- 既定の流れは `要件整理 -> 調査 -> 実行計画立案 -> 計画レビュー -> 詳細設計 -> 詳細設計レビュー -> 文書通読レビュー -> 実装` です。
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別 subagent で行います。
- `詳細設計レビュー` を通す前に実装へ進みません。
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認します。
- 長文では、`document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します。
