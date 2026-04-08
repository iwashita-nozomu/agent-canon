# Agent Hub

このディレクトリは、repo におけるエージェント運用の人間向け正本ハブです。
個別エージェント向けの runtime entrypoint は薄く保ち、詳細はここへ集約します。
この template では、Python 実装、pytest/pyright/ruff、Markdown 文書と report review を常設前提にします。
skill を user-facing に明示するときは `$skill-name` を第一推奨にします。

## 正本

- [canonical/README.md](/mnt/l/workspace/project_template/agents/canonical/README.md)
  - 共通レイアウトと正本の置き場
- [agents_config.json](/mnt/l/workspace/project_template/agents/agents_config.json)
  - チーム定義と write policy
- [TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
  - workflow family と task 選択
- [COMMUNICATION_PROTOCOL.md](/mnt/l/workspace/project_template/agents/COMMUNICATION_PROTOCOL.md)
  - handoff / review / escalation の正本
- [task_catalog.yaml](/mnt/l/workspace/project_template/agents/task_catalog.yaml)
  - machine-readable catalog
- [canonical/ARTIFACT_PLACEMENT.md](/mnt/l/workspace/project_template/agents/canonical/ARTIFACT_PLACEMENT.md)
  - task 文書と run artifact の置き分け
- [canonical/CLI_ENTRYPOINTS.md](/mnt/l/workspace/project_template/agents/canonical/CLI_ENTRYPOINTS.md)
  - agent ごとの入口差分と bootstrap 入口
- [canonical/CODEX_WORKFLOW.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_WORKFLOW.md)
  - Codex の標準 task 実行フロー
- [canonical/CODEX_SUBAGENTS.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_SUBAGENTS.md)
  - Codex の subagent routing
- [skills/README.md](/mnt/l/workspace/project_template/agents/skills/README.md)
  - 人間向け skill 正本
- [skills/catalog.yaml](/mnt/l/workspace/project_template/agents/skills/catalog.yaml)
  - skill family の機械可読カタログ
- [skills/literature-survey.md](/mnt/l/workspace/project_template/agents/skills/literature-survey.md)
  - 文献調査と先行研究整理の入口
- [skills/research-workflow.md](/mnt/l/workspace/project_template/agents/skills/research-workflow.md)
  - 研究系変更の outer loop
- [skills/adaptive-improvement-loop.md](/mnt/l/workspace/project_template/agents/skills/adaptive-improvement-loop.md)
  - 実験、調査、チューニング、比較改良の outer loop
- [skills/worktree-start.md](/mnt/l/workspace/project_template/agents/skills/worktree-start.md)
  - worktree kickoff、scope 初期化、action log 起点の固定
- [skills/long-form-writing.md](/mnt/l/workspace/project_template/agents/skills/long-form-writing.md)
  - README、workflow、guide などの長文作成フロー
- [skills/academic-writing.md](/mnt/l/workspace/project_template/agents/skills/academic-writing.md)
  - 論文、thesis chapter、scholarly note の作成フロー
- [skills/comprehensive-development.md](/mnt/l/workspace/project_template/agents/skills/comprehensive-development.md)
  - 包括的 repo-wide delivery の umbrella workflow
- [skills/environment-maintenance.md](/mnt/l/workspace/project_template/agents/skills/environment-maintenance.md)
  - Docker、CI、tool 導入方針の正本

## Runtime Entry Points

- [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
  - Codex / Copilot agent mode の入口
- [CLAUDE.md](/mnt/l/workspace/project_template/CLAUDE.md)
  - Claude Code の入口
- [.github/copilot-instructions.md](/mnt/l/workspace/project_template/.github/copilot-instructions.md)
  - GitHub Copilot repository instructions
- [.github/AGENTS.md](/mnt/l/workspace/project_template/.github/AGENTS.md)
  - GitHub 側の薄い入口

## Skills And Subagents

- Canonical project skills: `.agents/skills/`
- Claude compatibility mirror: `.claude/skills/` (generated from `.agents/skills/`)
- Claude subagents: `.claude/agents/`
- Codex runtime config: `.codex/`

## Team Shape

- Always-on roles:
  - `manager`, `manager_reviewer`, `designer`, `design_reviewer`, `document_flow_reviewer`, `implementer`, `change_reviewer`, `final_reviewer`, `verifier`, `auditor`
- Specialist roles:
  - `researcher`, `research_reviewer`, `experimenter`, `experiment_reviewer`, `scheduler`, `schedule_reviewer`, `infra_steward`, `infra_reviewer`, `notation_definition_reviewer`, `logic_gap_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer`, `critical_guardian`
- `manager` は intake、context sweep、library sweep、routing declaration、specialist activation の front door です。
- `designer` は常に `implementer` より前に走ります。
- review の直後は、直前の execution role が feedback を反映してから次段へ進みます。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は必ず別 instance にします。
- code 変更では `test_designer` を実装前に立て、最も意地の悪い case を `test_plan.md` に固定します。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` もそれぞれ別 instance にします。
- `implementer` だけが repo file を編集します。
- `manager`、reviewer 群、`researcher`、`scheduler`、`infra_steward`、`verifier`、`auditor` は artifact-only です。

## Startup Contract

- 着手時は `workflow=<family>`, `skills=<...>`, `review=<...>` を 1 行で宣言します。
- repo-changing task では、実装前に run bundle を作り、stage ごとの role / subagent を明示します。
- 包括的開発では、bundle に加えて `project_reviewer`、必要なら `docs_workflow_steward` と `python_reviewer` を明示します。
- 包括的開発では、`project_reviewer`、`docs_workflow_steward`、`python_reviewer` を固定 stack にします。
- planning を含む Codex session では、parent session 側の plan-mode command を使います。official Codex CLI では `/plan` です。
- Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、提供しない runtime では `.codex/agents/*.toml` を見ます。

## Standard Commands

明示的な skill 指定例:

```text
$repo-onboarding
$research-workflow
$adaptive-improvement-loop
$paper-writing
```

repo-changing task の最小 bundle:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

調査つき変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境・Docker・CI 変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発では、同一 worktree の writer は常に 1 人です。複数 writer が必要な場合は worktree を分けます。

`--task-id` を使うと、task catalog の default specialist と default review pack をそのまま bundle に展開できます。狭い例外だけ `--enable` を追加します。

## 運用ルール

- 共通方針は `agents/` 配下に集約し、entrypoint へ重複記述しません。
- 新しい workflow や skill を追加するときは、まず `agents/canonical/` の文書を更新します。
- 実行環境固有の都合がある場合だけ、`AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md` に最小限の差分を持たせます。
- 会話だけを根拠に実装へ進めず、`documents/`、`notes/`、`references/` と local library を先に探索します。
- reuse sweep をせずに新しい file や module を増やしません。
- stage reviewer の feedback を反映せずに次段へ handoff しません。
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしません。
- user-facing completion は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になるまで返しません。
