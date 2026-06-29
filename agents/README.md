<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Hub for this repository.
upstream design ../README.md shared canon overview
@dependency-end
-->

# Agent Hub


このディレクトリは、repo におけるエージェント運用の人間向け正本ハブです。
個別エージェント向けの runtime entrypoint は薄く保ち、詳細はここへ集約します。
この template では、Python 実装、pytest/pyright/ruff、Markdown 文書と report review を常設前提にします。
skill を user-facing に明示するときは `$skill-name` を使います。

## Reader Map

- この文書は、AgentCanon の人間向け agent hub として workflow、skill、subagent、runtime entrypoint への入口を所有します。
- `## Hub Routes` は目的別入口、`## Runtime Entry Points` と `## Skills And Subagents` は runtime surface、`## Team Shape` 以降は role と startup / command contract を扱います。
- 全体の読み順は root `README.md` の目的別ルートが正本です。この hub は、agent runtime、workflow、skill、subagent のどこを開くかだけを決めます。
- chunked reading では、まず `## Hub Routes` で入口を選び、`agents/canonical/README.md` は layout appendix として必要時だけ参照します。

## Hub Routes

| 目的 | 入口 | 役割 |
| --- | --- | --- |
| workflow family を選ぶ | [TASK_WORKFLOWS.md](TASK_WORKFLOWS.md), [workflows/README.md](workflows/README.md) | task family、stage、review route を決める |
| team shape と spawn budget を見る | [agents_config.json](agents_config.json), [task_catalog.yaml](task_catalog.yaml) | role、write policy、default specialist を固定する |
| handoff / review の契約を見る | [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md), [canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md) | subagent input packet、review separation、lifecycle を決める |
| Codex task の実行順を見る | [canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md), [canonical/CLI_ENTRYPOINTS.md](canonical/CLI_ENTRYPOINTS.md) | bootstrap、plan、implementation、closeout の順序を確認する |
| run artifact の置き場を確認する | [canonical/ARTIFACT_PLACEMENT.md](canonical/ARTIFACT_PLACEMENT.md) | reports、issues、notes、experiments の責務を分ける |
| skill を選ぶ | [skills/README.md](skills/README.md), [skills/catalog.yaml](skills/catalog.yaml) | 個別 skill 文書へ進む前に family と trigger を決める |
| internal routine を確認する | [internal-routines/README.md](internal-routines/README.md) | workflow が呼ぶ review / validation / compatibility routine を見る |

個別 skill のリンク一覧は `skills/README.md` と `skills/catalog.yaml` に集約します。
この hub には常用 skill の抜粋を増やしません。

## Runtime Entry Points

- [AGENTS.md](../AGENTS.md)
  - Codex agent mode の入口
- [.github/AGENTS.md](../.github/AGENTS.md)
  - GitHub 側の薄い入口

## Skills And Subagents

- Public Codex skill discovery: `.agents/skills/`
- Human-readable public skill docs: `agents/skills/`
- Workflow-routed internal and compatibility routines: `agents/internal-routines/`
- Codex runtime config and subagent registry: `.codex/config.toml`
- Codex role behavior: `.codex/agents/*.toml`
- Eval manifest source contracts: `evidence/agent-evals/`

## Team Shape

- Full staged always-on roles:
  - `manager`, `manager_reviewer`, `designer`, `design_reviewer`, `document_flow_reviewer`, `implementer`, `change_reviewer`, `final_reviewer`, `verifier`, `auditor`
- Lite scoped always-on roles:
  - `manager`, `implementer`, `change_reviewer`, `verifier`, `auditor`
- Specialist roles:
  - `researcher`, `research_reviewer`, `experimenter`, `experiment_reviewer`, `scheduler`, `schedule_reviewer`, `infra_steward`, `infra_reviewer`, `prompt_config_reviewer`, `project_reviewer`, `notation_definition_reviewer`, `logic_gap_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer`
- `manager` は intake、context sweep、library sweep、routing declaration、specialist activation の front door です。
- `designer` は常に `implementer` より前に走ります。
- review の直後は、直前の execution role が feedback を反映してから次段へ進みます。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は必ず別 instance にします。
- behavior-changing、regression-prone、または high-risk code 変更では
  `test_designer` を実装前に立て、最も意地の悪い case を `test_plan.md` に固定します。
  contract-only wrapper では checker-owned validation と static contract evidence を使います。
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

repo-changing task の基本 bundle:

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
- 実行環境固有の都合がある場合だけ、`AGENTS.md` にその環境で必要な差分を持たせます。
- 会話だけを根拠に実装へ進めず、`documents/`、`notes/`、`references/`、dependency surface、local implementation を先に探索します。
- reuse sweep をせずに新しい file や module を増やしません。
- 既存実装を使えるか、導入済みライブラリを拡張できるか、既存では足りない理由が何かを artifact に残さずに新規実装へ進めません。
- stage reviewer の feedback を反映せずに次段へ handoff しません。
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしません。
- tracked repo change で push が自然な完了条件なら、push の許可を取りに戻らず実行します。止めるのは user が明示的に止めた場合か external block がある場合だけです。
- user-facing completion は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved`、`mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked` になり、run-local diff-check artifact が現在 tracked diff ref（clean なら `HEAD`、dirty なら `HEAD-dirty-<sha256>`）の read-only independent approval を示すまで返しません。
