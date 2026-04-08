# comprehensive-development

## Purpose

code、docs、tests、workflow、tools、runtime をまたぐ repo-wide な変更を、1 本の umbrella workflow と explicit subagent routing で進めます。

## Use When

- implementation、docs、tooling、Docker、CI を同時に整理する
- agent canon、workflow、entrypoint、validation tool をまとめて改造する
- 1 つの局所 diff ではなく、複数 surface の整合を取りながら delivery したい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `documents/implementation-waterfall-workflow.md`
- `agents/skills/subagent-bootstrap.md`

## Standard Bundle

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

Codex overlay:

- `project_reviewer`
- `docs_workflow_steward`
- 必要に応じて `python_reviewer`

## Default Sequence

1. `agent-orchestration` で family を `Comprehensive Development` に固定します。
1. `subagent-bootstrap` で run bundle を作り、`workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します。
1. parent session が planning を含むなら `/collab` の `Plan` mode を先に有効化します。
1. runtime が対応していれば `/agent` で inventory を確認し、`project_reviewer`、`docs_workflow_steward`、`python_reviewer` の追加有無を決めます。
1. `project_reviewer` を intake overlay として立て、repo-wide completeness と collision risk を先に見ます。
1. `execution_planner` に stage order と `Write Scope Per Agent:` を書かせます。
1. `plan_reviewer` に review separation、rollback point、parallel write safety を見させます。
1. `detailed_designer` と `detailed_design_reviewer` を通したあと、長文があるなら `document_flow_reviewer` と docs reviewer を通します。
1. `worker` は bounded slice だけを担当し、親が 1 本ずつ統合します。
1. `project_reviewer` を closeout に再投入し、slice ごとではなく全体の integration risk を閉じます。

## Parallel Write Rule

- same file は 1 人の writer にしか割り当てません。
- same directory を複数 worker が触る場合は、file 単位の disjoint write scope を `schedule.md` に書きます。
- file 境界を切れない場合は、parallel write をやめるか別 worktree に分けます。
- reviewer は read-only を保ち、write collision を plan review で潰します。

## Boundary

- 局所修正なら `Scoped Change` を使います。
- chunk ごとに独立 pass を閉じたい delivery なら `Large Delivery` を使います。
- Docker / CI が中心なら `Platform And Environment` を使います。
- 外部調査と experiment が主役なら `Research-Driven Change` を使います。
