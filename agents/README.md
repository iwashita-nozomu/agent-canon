# Agent Hub

このディレクトリは、repo におけるエージェント運用の人間向け正本ハブです。
個別エージェント向けの runtime entrypoint は薄く保ち、詳細はここへ集約します。
この template では、Python 実装、pytest/pyright/ruff、Markdown 文書と report review を常設前提にします。

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
- [skills/experiment-change-loop.md](/mnt/l/workspace/project_template/agents/skills/experiment-change-loop.md)
  - 実験結果に基づく改造 loop の自律実行
- [skills/worktree-start.md](/mnt/l/workspace/project_template/agents/skills/worktree-start.md)
  - worktree kickoff、scope 初期化、action log 起点の固定
- [skills/long-form-writing.md](/mnt/l/workspace/project_template/agents/skills/long-form-writing.md)
  - README、workflow、guide などの長文作成フロー
- [skills/academic-writing.md](/mnt/l/workspace/project_template/agents/skills/academic-writing.md)
  - 論文、thesis chapter、scholarly note の作成フロー
- [skills/from_another_agent.md](/mnt/l/workspace/project_template/agents/skills/from_another_agent.md)
  - 前回 agent run の carry-over note を current task へ接続
- [skills/project-review.md](/mnt/l/workspace/project_template/agents/skills/project-review.md)
  - repo-wide review と棚卸し
- [skills/comprehensive-development.md](/mnt/l/workspace/project_template/agents/skills/comprehensive-development.md)
  - 包括的 repo-wide delivery の umbrella workflow
- [skills/research-perspective-review.md](/mnt/l/workspace/project_template/agents/skills/research-perspective-review.md)
  - 研究系変更の並列 review pack
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
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` もそれぞれ別 instance にします。
- `implementer` だけが repo file を編集します。
- `manager`、reviewer 群、`researcher`、`scheduler`、`infra_steward`、`verifier`、`auditor` は artifact-only です。

## Startup Contract

- 着手時は `workflow=<family>`, `skills=<...>`, `review=<...>` を 1 行で宣言します。
- repo-changing task では、実装前に run bundle を作り、stage ごとの role / subagent を明示します。
- 包括的開発では、bundle に加えて `project_reviewer`、必要なら `docs_workflow_steward` と `python_reviewer` を明示します。
- planning を含む Codex session では、可能なら `/collab` で `Plan` mode に切り替えます。
- Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、提供しない runtime では `.codex/agents/*.toml` を見ます。

## Standard Commands

repo-changing task の最小 bundle:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer
```

調査つき変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable researcher \
  --enable research_reviewer \
  --enable experimenter \
  --enable experiment_reviewer
```

学術文章:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable researcher \
  --enable research_reviewer \
  --enable notation_definition_reviewer \
  --enable logic_gap_reviewer
```

環境・Docker・CI 変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable infra_steward \
  --enable infra_reviewer
```

包括的開発:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable researcher \
  --enable research_reviewer \
  --enable infra_steward \
  --enable infra_reviewer \
  --enable critical_guardian
```

同じディレクトリを複数 worker が触っても構いませんが、same file は 1 人の writer にしか割り当てません。境界が曖昧なら parent が直列化するか別 worktree に分けます。

`scheduler` と `schedule_reviewer` のような paired specialist は同じ activation group を共有しますが、bundle の意図を曖昧にしないため両方を明示して構いません。

## 運用ルール

- 共通方針は `agents/` 配下に集約し、entrypoint へ重複記述しません。
- 新しい workflow や skill を追加するときは、まず `agents/canonical/` の文書を更新します。
- 実行環境固有の都合がある場合だけ、`AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md` に最小限の差分を持たせます。
- 会話だけを根拠に実装へ進めず、`documents/`、`notes/`、`references/` と local library を先に探索します。
- reuse sweep をせずに新しい file や module を増やしません。
- stage reviewer の feedback を反映せずに次段へ handoff しません。
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしません。
