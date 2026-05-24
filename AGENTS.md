# AgentCanon Repository Instructions
<!--
@dependency-start
responsibility Documents AgentCanon Repository Instructions for this repository.
downstream design README.md shared canon overview must reflect runtime contract
@dependency-end
-->


この tree は standalone AgentCanon repo の source of truth です。
template / derived repo では `vendor/agent-canon/` submodule pin として参照されます。
ここを単体で見ているときは、shared canon の整合を優先し、特定の派生 repo に閉じた Docker、implementation、experiment 前提を持ち込みません。

## Read First

- `README.md`
- `agents/README.md`
- `agents/canonical/README.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/worktree-lifecycle.md`
- `.codex/README.md`

## Scope

- root AGENTS runtime wrapper
- Claude / Copilot runtime entrypoints
- shared Codex config defaults
- shared agent workflow
- shared skill canon
- Codex / Claude subagent inventory
- agent review / coordination documents
- shared runtime surface ownership document
- submodule update and legacy migration operation canon
- skill and worktree operation canon
- carry-over note template
- worktree note templates
- agent-specific CI workflow
- agent-specific regression tests
- agent support scripts

## Non-Goals

- `docker/`
- shared canon の外にある repo-local `python/`
- `experiments/`
- repo-local README / bootstrap / server contract

## Working Rule

- AgentCanon tree changes は shared canon として成立するかを先に確認する
- 広い概念、長い user request、文書統合、薄い文書洗い出しでは、広域 `rg` の前に `agent-canon semantic-index search --query-file <file> --top-k <N> --format text|jsonl` または `agent-canon semantic-index thin-docs --top-k <N> --format text` を試す
- root entrypoint wrapper の変更は、この tree ではなく template / 派生 repo 側の wrapper task として扱う
