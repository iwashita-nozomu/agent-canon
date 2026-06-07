<!--
@dependency-start
responsibility Documents Agent Hub for this repository.
upstream design ../README.md shared canon overview
@dependency-end
-->

# Agent Hub


このディレクトリは、repo におけるエージェント運用の人間向け正本ハブです。
個別エージェント向けの runtime entrypoint は薄く保ち、詳細はここへ集約します。
この template では、Python 実装、pytest/pyright/ruff、Markdown 文書と report review を常設前提にします。
skill を user-facing に明示するときは `$skill-name` を使います。

## Recommended Read Order

1. `README.md`
1. `documents/README.md`
1. `agents/README.md`
1. `agents/workflows/README.md`

`agents/canonical/README.md` は layout appendix です。最初の人間向け hub として
使わず、この file から必要になったときだけ参照します。

## 正本

- [canonical/README.md](canonical/README.md)
  - 共通レイアウトと正本の置き場を説明する appendix
- [agents_config.json](agents_config.json)
  - チーム定義と write policy
- [TASK_WORKFLOWS.md](TASK_WORKFLOWS.md)
  - workflow family と task 選択
- [workflows/README.md](workflows/README.md)
  - workflow catalog と routing guide の入口
- [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md)
  - handoff / review / escalation の正本
- [task_catalog.yaml](task_catalog.yaml)
  - machine-readable catalog
- [canonical/ARTIFACT_PLACEMENT.md](canonical/ARTIFACT_PLACEMENT.md)
  - task 文書と run artifact の置き分け
- [canonical/CLI_ENTRYPOINTS.md](canonical/CLI_ENTRYPOINTS.md)
  - agent ごとの入口差分と bootstrap 入口
- [canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md)
  - Codex の標準 task 実行フロー
- [canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md)
  - Codex の subagent routing
- [skills/README.md](skills/README.md)
  - 人間向け skill 正本
- [skills/catalog.yaml](skills/catalog.yaml)
  - skill family の機械可読カタログ
- [skills/literature-survey.md](skills/literature-survey.md)
  - 文献調査と先行研究整理の入口
- [skills/formal-proof-workflow.md](skills/formal-proof-workflow.md)
  - 自然言語 claim から形式証明 scaffold と checker evidence へ進む入口
- [skills/research-workflow.md](skills/research-workflow.md)
  - 研究系変更の outer loop
- [skills/adaptive-improvement-loop.md](skills/adaptive-improvement-loop.md)
  - 実験、調査、チューニング、比較改良の outer loop
- [skills/worktree-start.md](skills/worktree-start.md)
  - worktree kickoff、scope 初期化、action log 起点の固定
- [skills/long-form-writing.md](skills/long-form-writing.md)
  - README、workflow、guide、migration、specification など一般説明 prose の DSL-to-prose adapter
- [skills/academic-writing.md](skills/academic-writing.md)
  - 論文、thesis chapter、scholarly note の作成フロー
- [skills/comprehensive-development.md](skills/comprehensive-development.md)
  - 包括的 repo-wide delivery の umbrella workflow
- [skills/environment-maintenance.md](skills/environment-maintenance.md)
  - Docker、CI、tool 導入方針の正本

## Runtime Entry Points

- [AGENTS.md](../AGENTS.md)
  - Codex agent mode の入口
- [.github/AGENTS.md](../.github/AGENTS.md)
  - GitHub 側の薄い入口

## Skills And Subagents

- Public Codex skill discovery: `.agents/skills/`
- Human-readable public, internal, and compatibility skill docs: `agents/skills/`
- Codex runtime config and subagent registry: `.codex/config.toml`
- Codex role behavior: `.codex/agents/*.toml`
- Eval manifest source contracts: `evidence/agent-evals/`

## Team Shape

- Full staged always-on roles:
  - `manager`, `manager_reviewer`, `designer`, `design_reviewer`, `document_flow_reviewer`, `implementer`, `change_reviewer`, `final_reviewer`, `verifier`, `auditor`
- Lite scoped always-on roles:
  - `manager`, `implementer`, `change_reviewer`, `verifier`, `auditor`
- Specialist roles:
  - `researcher`, `research_reviewer`, `experimenter`, `experiment_reviewer`, `scheduler`, `schedule_reviewer`, `infra_steward`, `infra_reviewer`, `prompt_config_reviewer`, `notation_definition_reviewer`, `logic_gap_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer`, `critical_guardian`
- `manager` は intake、context sweep、library sweep、routing declaration、specialist activation の front door です。
- `designer` は常に `implementer` より前に走ります。
- review の直後は、直前の execution role が feedback を反映してから次段へ進みます。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は必ず別 instance にします。
- code 変更では `test_designer` を実装前に立て、最も意地の悪い case を `test_plan.md` に固定します。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` もそれぞれ別 instance にします。
- repo file edit は parent-managed write scope で割り当て、同一 path / ownership / public API surface を複数 writer に割り当てません。
- `manager`、reviewer 群、`researcher`、`scheduler`、`infra_steward`、`verifier`、`auditor` は artifact-only です。

## Startup Contract

- 着手時は `workflow=<family>`, `skills=<...>`, `review=<...>` を 1 行で宣言します。
- repo-changing task では、実装前に run bundle を作り、stage ごとの role / subagent を明示します。
- 包括的開発の route は [skills/comprehensive-development.md](skills/comprehensive-development.md) に集約し、この hub では bootstrap command と review stack の入口だけを示します。
- 包括的開発では、`project_reviewer`、`docs_workflow_steward`、prompt/config surface があれば `prompt_config_reviewer`、言語差分に応じた reviewer を bundle に明示します。
- planning を含む Codex session では、parent session 側の plan-mode command を使います。official Codex CLI では `/plan` です。
- Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、提供しない runtime では `.codex/agents/*.toml` を見ます。

## Standard Commands

明示的な skill 指定例:

```text
$repo-onboarding
$research-workflow
$formal-proof-workflow
$adaptive-improvement-loop
$paper-writing
```

repo-changing task の最小 bundle:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

調査つき変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境・Docker・CI 変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発では、parent が `team_manifest.yaml` の write policy で writer ごとの path / directory を管理します。scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。

`--task-id` を使うと、task catalog の default specialist と default review pack をそのまま bundle に展開できます。狭い例外だけ `--enable` を追加します。

## 運用ルール

- 共通方針は `agents/` 配下に集約し、entrypoint へ重複記述しません。
- workflow family 選択はこの hub と `workflows/README.md` を正本にし、`canonical/README.md` を第二の hub にしません。
- 新しい workflow や skill を追加するときは、まず `agents/canonical/` の文書を更新します。
- 実行環境固有の都合がある場合だけ、`AGENTS.md` に最小限の差分を持たせます。
- 会話だけを根拠に実装へ進めず、`documents/`、`notes/`、`references/`、dependency surface、local implementation を先に探索します。
- reuse sweep をせずに新しい file や module を増やしません。
- 既存実装を使えるか、導入済みライブラリを拡張できるか、既存では足りない理由が何かを artifact に残さずに新規実装へ進めません。
- stage reviewer の feedback を反映せずに次段へ handoff しません。
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしません。
- tracked repo change で push が自然な完了条件なら、push の許可を取りに戻らず実行します。止めるのは user が明示的に止めた場合か external block がある場合だけです。
- user-facing completion は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved`、`mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked` になり、run-local diff-check artifact が現在 tracked diff ref（clean なら `HEAD`、dirty なら `HEAD-dirty-<sha256>`）の read-only independent approval を示すまで返しません。
