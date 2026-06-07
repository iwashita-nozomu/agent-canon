# codex-task-workflow

<!--
@dependency-start
responsibility Documents codex-task-workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest requirements
upstream design tool-finding-report.md tool-based finding packet and prompt feedback workflow
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
1. execution plan and plan review for full staged routes
1. detailed design and detailed design review for full staged routes
1. document flow review for reader-facing docs, new terms, public APIs, or full staged routes
1. implementation
1. validation
1. closeout

## Required Output

- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- Shared canon / Large delivery / high-risk / multi-step task では `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
- `Scoped Change Lite` では cheap-first local route を使い、document-flow / broad design review は escalation 条件がある場合だけ起動する
- Routine docs / Focused code では parent-direct を許可し、必要な targeted validation を通す
- repo-changing task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` は subagent が必要な risk class でだけ併用する
- workflow family、public skill set、review stack は `agent-orchestration` の出力を入力として受け取り、この skill で routing matrix を重複定義しない
- AgentCanon update surface が repairable なら `make agent-canon-ensure-latest` を実行する。submodule repo では親 repo の無関係な dirty state はこの実行を block しない。update surface 自体が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon PR / proposal merge 後に `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰る
- 普通の相談、壁打ち、routing-only advice、説明だけの turn はこの skill の実行対象ではありません。その場合は `check_mcp_inventory.py`、repo MCP tools、shell / GitHub checks を走らせず、会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させない。迷う場合は `agent-canon mcp-preflight-policy --request-kind github-actions-read` で `MCP_PREFLIGHT_DECISION=skip` を確認する
- repository task の intake では、MCP evidence が workflow 上必要か、または `.codex/config.toml`、`mcp/`、repo MCP tools、MCP-dependent goal-loop gate を編集するかを判定する。必要な場合だけ `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` を実行し、pass したら repo MCP tools を repo root / status / context 確認の優先候補にする。run bundle へ monitoring evidence を追記したい場合だけ `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` を併用する
- Rust CLI または local Cargo が AgentCanon の lockfile を読めない場合は `mcp_preflight_unavailable=<reason>` を記録し、MCP runtime behavior そのものが task scope でない限り既存 Python / shell gate で検証を続ける
- AgentCanon owns the repo MCP implementation in `mcp/repo_mcp_server.sh`, `mcp/repo_mcp_server.py`, and `mcp/README.md`; Codex owns `.codex/config.toml` registration, project trust, hooks, apps, external connectors, and session tool availability
- current `repo_mcp_server` は status/context 専用なので、file editing capability が無いことを毎回 user update で説明しない。MCP failure / mismatch または user の質問がある場合だけ説明する
- `repo_mcp_server` に file edit、GitHub connector、shell runner、web access、Codex app の代替を実装しない。必要な capability は Codex-provided tool / connector surface を使う
- 編集手段は、小〜中規模は patch-based edit、機械生成・一括変換は repo script / formatter、MCP editing は explicit edit tool 実装後、の順に選ぶ
- 詳細設計が編集対象 path に絞る前に、責務 model、概念 graph または layer model、非対象、将来拡張 layer、評価軸、canonical surface 関係を含む `Abstract Design Frame` を書くか引用する。実装 scope、file list、validation は nearest editable path や current finding ではなく、この frame から導く
- 実装前に承認済み `design_brief.md` の `Abstract Design Frame`、`Implementation Source Packet`、`Design-To-Implementation Trace` を読み、各 implementation slice が抽象責務 model から導かれていることを確認してから design artifact path、design section、test-plan item、user-request clause ID を引用する
- 実装前に `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら Abstract Design Frame と design trace から導かれた narrow slice は `spark_worker` を先に使う
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- parent 直編集でも write-capable subagent でも、実装前に cause investigation artifact を固定し、`Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残してから code edit に入る
- parent 直編集でも write-capable subagent でも、実装前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、予測された cause investigation / OOP / helper / dependency / hook runtime / skill mirror / tool catalog / protocol / log-surface gate と repair plan を handoff または work log に残す
- tool / checker / hook / reviewer / subagent feedback から実装へ入る場合は `tool-finding-report` で finding packet を作り、write-capable subagent handoff に artifact path、structured findings、prompt feedback decision を渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` が出た場合は、次の write-capable subagent を起動する前に handoff prompt、skill、workflow、または task catalog prompt を修正する
- prompt/config drift が shared canon surface をまたぐ場合は、親がその場で prose を増やす前に `prompt_config_reviewer` で audit し、この workflow はその監査結果を消費して最小差分だけ適用する
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
- Shared canon / Large delivery / high-risk / workflow-tooling change では closeout 前に `python3 tools/agent_tools/check_convention_compliance.py` を通し、workflow prohibition、convention tool gate、skill-routing hook の欠落を tool で検出する
