<!--
@dependency-start
contract reference
responsibility Documents エージェント利用ガイド for this repository.
upstream design README.md agent canon overview
@dependency-end
-->

# エージェント利用ガイド


## この文書の読み方

この文書は、AgentCanon を使う読者向けの入口案内です。まず
`どこから読むか` と `入口の使い分け` で runtime ごとの入口を選び、
`skill の使い方` で task 形状に合う skill を確認します。repo-changing task や
複数 agent を使う場合は `subagent の使い方` を読みます。この文書は利用案内であり、
workflow family、role behavior、validation gate の正本はリンク先の owner surface です。

## どこから読むか

1. [agents/README.md](README.md)
1. [agents/canonical/README.md](canonical/README.md)
1. [agents/TASK_WORKFLOWS.md](TASK_WORKFLOWS.md)
1. [agents/skills/README.md](skills/README.md)

## 入口の使い分け

- Codex runtime:
  - [AGENTS.md](../AGENTS.md)
  - [.codex/README.md](../.codex/README.md)

## skill の使い方

- 共通 skill の正本は `.agents/skills/` にあります。
- skill を明示したいときは `$skill-name` を使います。
- 例: `$repo-onboarding`、`$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`
- plain text で skill 名を書く運用もできますが、既定表記は `$skill-name` です。
- どの skill を使うか迷う場合は、まず `repo-onboarding` か `codex-task-workflow` を見ます。
- Codex で毎回同じ手順を踏みたい場合は `codex-task-workflow` を見ます。
- Python 差分では `python-review` を既定で使います。
- C / C++ 差分では `cpp-review` を既定で使います。
- 局所 diff を findings-first で見るときは `change-review` を使います。
- Markdown 差分では `md-style-check` を使います。
- 文書構造、reader path、claim support、source map、canonical route、document responsibility が変わる Markdown 差分では、`structure-planning` と `prose-reasoning-graph` を先に使い、closeout の `Document Structure Evidence` に構造解析 evidence を残します。
- typo / link / format-only の Markdown 差分では、`md-style-check` と `structure_contract=skipped:<reason>` を evidence に残します。
- owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じた repo-changing 差分では `owner-bounded-routing` を使い、existing tool を読了 gate なしに先に実行し、owner boundary、existing-tool route、targeted validation を evidence に残します。
- README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書では、`long-form-writing` を DSL-to-prose adapter として使います。長さだけでは選びません。
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

- Codex 用 subagent は `.codex/agents/` にあります。
- subagent は task 固有に使い、repo 全体の正本は `agents/` 側に置きます。
- repo-changing task では run bundle を先に作ります。
- 着手時は `workflow=<family>`, `skills=<...>`, `review=<...>` を 1 行で宣言します。
- `skills=<...>` には `$skill-name` で指定した skill をそのまま並べます。
- 例: `skills=$research-workflow,$literature-survey,$paper-writing`
- 既定の流れは workflow family で変わります。owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じている修正は `Owner-Bounded Change`、それ以外の repo-changing task は `要件整理 -> 調査 -> 実行計画立案 -> 計画レビュー -> 詳細設計 -> 詳細設計レビュー -> 文書通読レビュー -> 実装` を基準にします。
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` は別 subagent で行います。
- `詳細設計レビュー` を通す前に実装へ進みません。
- observable behavior、regression risk、または test contract を変える code 変更では `test_designer` を別 instance で立て、実装前に nasty case を洗います。contract-only wrapper は static contract validation と canonical command evidence を使います。
- 包括的開発では、parent が writer ごとの path / directory を `team_manifest.yaml` の write policy で管理します。
- write scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認します。
- 一般説明 prose adapter を使う文書では、`document_flow_reviewer` に加えて別 reviewer で docs completeness review を通します。
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
