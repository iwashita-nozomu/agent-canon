# subagent-bootstrap
<!--
@dependency-start
responsibility Documents subagent-bootstrap for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

specialist delegation が必要な task で、run bundle、役割分担、write-scope を崩さずに起動します。

## Use When

- run artifact を残したい
- specialist を使う
- reviewer / implementer の責務を分けたい
- 計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent を分けたい
- `/goal` 確定前に read-only subagent、または明示許可待ちの handoff plan で goal draft、repo survey、first-slice plan を固めたい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `tools/agent_tools/bootstrap_agent_run.py`

## Standard Command

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "repo-changing task" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

研究・実験つき変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
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

包括的開発:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

repo-changing task では、`--task-id` を使って task catalog の default specialist と default review pack をそのまま有効化します。
goal-driven repo-changing task では、`/goal` がまだ exact でなくても provisional run bundle を作り、`requirements_organizer`、`explorer`、必要なら `execution_planner` と `plan_reviewer` の read-only handoff plan を先に作ります。active runtime が明示許可を持つ場合だけ、その wave を起動します。
write-capable implementation subagent は `goal.md` が parseable で、Codex goal view が mirrored / queued され、Plan-mode evidence mapping が揃うまで起動しません。
active runtime が explicit user request なしの `spawn_agent` を禁止する場合、read-only pre-goal wave も即座には起動せず、handoff packet、owner、expected output、`PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を run bundle に残して許可待ちにします。
command output の `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら approved design packet で完全に切れる低リスク implementation slice は `spark_worker` を先に使います。
subagent の model / reasoning は `.codex/config.toml` の `agents.model_policy` を先に読みます。
repo inventory、tool drift survey、static validation triage、diff-local Python / C++ review、機械 report 要約は、明示許可がある場合に Spark bucket の read-only wave へ先に切ります。bounded review、report traceability、checklist-style review gate は mini review bucket へ先に切ります。parent は結果統合、設計判断、scope 判断、最終責任へ集中します。
実装 slice は 1 file または単一抽象ユニット、public interface 変更なし、依存追加なし、仕様解釈なし、局所 validation で閉じる場合だけ `spark_worker` first にします。
`explorer` などの project-defined Spark role が runtime tool compatibility で失敗した場合は、parent へ戻す前に fresh default subagent を `.codex/config.toml` の Spark bucket の `model` と `model_reasoning_effort` で再起動します。
command output の `WORKFLOW_SUBAGENT_PROMPT_PACKET` を確認し、すべての subagent handoff prompt に `team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` を含めます。
設計解釈、衝突解決、広い architecture 判断、scope 判断を含む implementation は `worker` に戻します。
調査、環境変更、学術文章、包括的開発の強い review coverage は task catalog 側の default として管理します。
code change では `test_designer` を実装前に立て、nasty case を `test_plan.md` に残します。
包括的開発では bundle に加えて `project_reviewer`、`docs_workflow_steward`、`python_reviewer`、必要に応じて `cpp_reviewer` を固定で立てます。
Codex で planning を含む parent session では、plan-mode command を先に使います。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。
計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent は、同じ instance を使い回しません。
学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance を使います。
包括的開発では、同一 worktree の writer を `worker` 1 人に固定します。複数 writer が必要な場合は worktree を分けます。
新規 user request では前 task の subagent に `send_input` せず、run bundle ごとに fresh subagent を起こします。
subagent handoff prompt には `team_manifest.yaml` の `run.subagent_lifecycle_policy` を含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を明示します。
closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` に close evidence を残します。
