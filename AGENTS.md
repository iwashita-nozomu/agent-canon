# agent-canon Snapshot Instructions
<!--
@dependency-start
responsibility Documents agent-canon Snapshot Instructions for this repository.
downstream design README.md shared canon overview must reflect runtime contract
@dependency-end
-->


この subtree は shared agent canon の snapshot です。
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
- subtree migration and sync operation canon
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

- subtree 内の変更は shared canon として成立するかを先に確認する
- root entrypoint wrapper の変更は、この subtree ではなく template / 派生 repo 側の wrapper task として扱う
