# codex-task-workflow

<!--
@dependency-start
responsibility Documents codex-task-workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest requirements
downstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

Codex が会話コンテキストに依存せず、毎回同じ順序で task を進めるための標準フローです。

## Use When

- Codex で task を最初から最後まで進める
- 手順を固定したい
- task ごとの skill 選択を標準化したい

## Core Reference

- `agents/canonical/CODEX_WORKFLOW.md`

## Stages

1. intake
1. required context and library sweep
1. workflow selection
1. artifact placement
1. explicit subagent bootstrap
1. execution plan and plan review
1. detailed design and detailed design review
1. document flow review
1. implementation
1. validation
1. closeout

## Required Output

- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- Shared canon / Large delivery / high-risk / multi-step task では `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
- Routine docs / Focused code では parent-direct を許可し、必要な targeted validation を通す
- repo-changing task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` は subagent が必要な risk class でだけ併用する
- AgentCanon update surface が repairable なら `make agent-canon-ensure-latest` を実行する。submodule repo では親 repo の無関係な dirty state はこの実行を block しない。update surface 自体が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon PR / proposal merge 後に `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰る
- 普通の相談、壁打ち、routing-only advice、説明だけの turn はこの skill の実行対象ではありません。その場合は `check_mcp_inventory.py`、repo MCP tools、shell / GitHub checks を走らせず、会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させない。迷う場合は `agent-canon mcp-preflight-policy --request-kind github-actions-read` で `MCP_PREFLIGHT_DECISION=skip` を確認する
- repository task の intake では、MCP evidence が workflow 上必要か、または `.codex/config.toml`、`mcp/`、repo MCP tools、MCP-dependent goal-loop gate を編集するかを判定する。必要な場合だけ `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` を実行し、pass したら repo MCP tools を repo root / status / context 確認の優先候補にする。run bundle へ monitoring evidence を追記したい場合だけ `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` を併用する
- Rust CLI または local Cargo が AgentCanon の lockfile を読めない場合は `mcp_preflight_unavailable=<reason>` を記録し、MCP runtime behavior そのものが task scope でない限り既存 Python / shell gate で検証を続ける
- AgentCanon owns the repo MCP implementation in `mcp/repo_mcp_server.sh`, `mcp/repo_mcp_server.py`, and `mcp/README.md`; Codex owns `.codex/config.toml` registration, project trust, hooks, apps, external connectors, and session tool availability
- current `repo_mcp_server` は status/context 専用なので、file editing capability が無いことを毎回 user update で説明しない。MCP failure / mismatch または user の質問がある場合だけ説明する
- `repo_mcp_server` に file edit、GitHub connector、shell runner、web access、Codex app の代替を実装しない。必要な capability は Codex-provided tool / connector surface を使う
- 編集手段は、小〜中規模は patch-based edit、機械生成・一括変換は repo script / formatter、MCP editing は explicit edit tool 実装後、の順に選ぶ
- 実装前に `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら design-traced narrow slice は `spark_worker` を先に使う
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- parent 直編集でも write-capable subagent でも、実装前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、予測された OOP / helper / dependency / hook runtime / skill mirror / tool catalog / protocol / log-surface gate と repair plan を handoff または work log に残す
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
- Shared canon / Large delivery / high-risk / workflow-tooling change では closeout 前に `python3 tools/agent_tools/check_convention_compliance.py` を通し、workflow prohibition、convention tool gate、skill-routing hook の欠落を tool で検出する
