# comprehensive-development

## Purpose

code、docs、tests、workflow、tools、runtime をまたぐ repo-wide な変更を、1 本の umbrella workflow と explicit subagent routing で進めます。
この skill では裁量を残さず、固定役割・固定順序・単一 writer で進めます。

## Use When

- implementation、docs、tooling、Docker、CI を同時に整理する
- agent canon、workflow、entrypoint、validation tool をまとめて改造する
- 1 つの局所 diff ではなく、複数 surface の整合を取りながら delivery したい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/workflows/implementation-waterfall-workflow.md`

## Standard Bundle

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

固定 Codex stack:

- `project_reviewer`
- `docs_workflow_steward`
- `test_designer`
- `python_reviewer`
- `cpp_reviewer`

## Default Sequence

1. family を `Comprehensive Development` に固定します。
1. run bundle を作り、`workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します。
1. parent session が planning を含むなら、plan-mode command を先に有効化します。official Codex CLI では `/plan` です。
1. `/agent` が使える runtime では inventory を確認し、使えない runtime では `.codex/agents/*.toml` をそのまま使います。
1. `project_reviewer` を intake gate として立て、repo-wide completeness と collision risk を先に見ます。
1. Python 差分なら `python_reviewer`、C / C++ 差分なら `cpp_reviewer` を早めに追加し、言語別の build / test / boundary risk を先に見ます。
1. `execution_planner` に stage order と `Write Scope Per Agent:` を書かせます。
1. `plan_reviewer` に review separation、rollback point、parallel write safety を見させます。
1. `detailed_designer` と `detailed_design_reviewer` を通したあと、長文があるなら `document_flow_reviewer` と docs reviewer を通します。
1. code 変更では `test_designer` を立てて static path と nasty case を `test_plan.md` に固定します。
1. `worker` は bounded slice だけを担当し、親が 1 本ずつ統合します。
1. `project_reviewer` を closeout に再投入し、slice ごとではなく全体の integration risk を閉じます。

## Single-Writer Rule

- 同一 worktree の writer は `worker` 1 人に固定します。
- same directory の parallel write を許可しません。
- 複数 writer が必要な場合は worktree を分け、各 worktree に writer を 1 人だけ置きます。
- reviewer は read-only を保ち、single-writer rule の確認は `plan_reviewer` と `project_reviewer` が行います。

## Boundary

- 局所修正なら `Scoped Change` を使います。
- chunk ごとに独立 pass を閉じたい delivery なら `Large Delivery` を使います。
- Docker / CI が中心なら `Platform And Environment` を使います。
- 外部調査と experiment が主役なら `Research-Driven Change` を使います。
