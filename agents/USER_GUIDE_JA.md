<!--
@dependency-start
responsibility Documents エージェント利用ガイド for this repository.
upstream design README.md agent canon overview
@dependency-end
-->

# エージェント利用ガイド


## どこから読むか

1. [agents/README.md](../../../agents/README.md)
1. [agents/canonical/README.md](../../../agents/canonical/README.md)
1. [agents/TASK_WORKFLOWS.md](../../../agents/TASK_WORKFLOWS.md)
1. [agents/skills/README.md](../../../agents/skills/README.md)

## 入口の使い分け

- Codex / Copilot agent mode:
  - [AGENTS.md](../../../AGENTS.md)
- Claude Code:
  - [CLAUDE.md](../../../CLAUDE.md)
- GitHub Copilot custom instructions:
  - [.github/copilot-instructions.md](../../../.github/copilot-instructions.md)

## skill の使い方

- 共通 skill の正本は `.agents/skills/` にあります。
- Claude では `.claude/skills/` の generated mirror を使います。正本は `.agents/skills/` です。
- skill を明示したいときは `$skill-name` を使います。
- 例: `$repo-onboarding`、`$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`
- plain text で skill 名を書く運用もできますが、既定表記は `$skill-name` です。
- どの skill を使うか迷う場合は、まず `repo-onboarding` か `codex-task-workflow` を見ます。
- Codex で毎回同じ手順を踏みたい場合は `codex-task-workflow` を見ます。
- Python 差分では `python-review` を既定で使います。
- C / C++ 差分では `cpp-review` を既定で使います。
- 局所 diff を findings-first で見るときは `change-review` を使います。
- Markdown 差分では `md-style-check` を使います。
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を使います。
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を使います。
- 投稿論文や thesis chapter の draft では `paper-writing` を使います。
- 文献調査や関連研究整理では `literature-survey` を使います。
- 研究系 task では `research-workflow` を外側の loop に使います。
- 実験結果を見ながら code change、調査、チューニングを継続反復する場合は `adaptive-improvement-loop` を使います。
- 単一 run の review / rerun 分岐は `experiment-lifecycle` を使います。
- worktree を切った直後は `worktree-start` で scope と action log を固定し、drift や cleanup 判断は `worktree-health` を使います。
- code、docs、tools、runtime をまとめて rework する包括的変更では `comprehensive-development` を使います。
- Docker、CI、dependency、repo-wide tool 導入案では `environment-maintenance` を使います。

## subagent の使い方

- Claude 専用 subagent は `.claude/agents/` にあります。
- Codex 用 subagent は `.codex/agents/` にあります。
- subagent は task 固有に使い、repo 全体の正本は `agents/` 側に置きます。
- repo-changing task では run bundle を先に作ります。
- 着手時は `workflow=<family>`, `skills=<...>`, `review=<...>` を 1 行で宣言します。
- `skills=<...>` には `$skill-name` で指定した skill をそのまま並べます。
- 例: `skills=$research-workflow,$literature-survey,$paper-writing`
- 既定の流れは `要件整理 -> 調査 -> 実行計画立案 -> 計画レビュー -> 詳細設計 -> 詳細設計レビュー -> 文書通読レビュー -> 実装` です。
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別 subagent で行います。
- `詳細設計レビュー` を通す前に実装へ進みません。
- code 変更では `test_designer` を別 instance で立て、実装前に nasty case を洗います。
- 包括的開発では、同一 worktree の writer を 1 人に固定します。
- 複数 writer が必要な場合は、同一 worktree ではなく複数 worktree に分けます。
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認します。
- 長文では、`document_flow_reviewer` に加えて別 reviewer で docs completeness review を通します。
- 学術文章では、さらに `notation_definition_reviewer` と `logic_gap_reviewer` を別 instance で通します。
- 論文 draft では、さらに `citation_evidence_reviewer` を別 instance で通します。
- 最後の user-facing 完了報告は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved`、`mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked` になり、run-local diff-check artifact が現在 tracked diff ref の read-only independent approval を示すまで出しません。

標準 bundle:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "repo-changing task" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

Codex で planning を含む session では、parent session 側の plan-mode command を先に使います。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。

包括的開発の標準 bundle:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```
