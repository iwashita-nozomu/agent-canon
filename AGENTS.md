# agent-canon Snapshot Instructions

この subtree は shared agent canon の snapshot です。
ここを単体で見ているときは、shared canon の整合を優先し、product 固有の Docker、implementation、experiment 前提を持ち込みません。

## Read First

- `README.md`
- `agents/README.md`
- `agents/canonical/README.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/AGENTS_COORDINATION.md`
- `.codex/README.md`

## Scope

- shared agent workflow
- shared skill canon
- Codex / Claude subagent inventory
- agent review / coordination documents
- agent support scripts

## Non-Goals

- `docker/`
- `python/`
- `experiments/`
- product-specific README / bootstrap / server contract

## Working Rule

- subtree 内の変更は shared canon として成立するかを先に確認する
- product root entrypoint の変更は、この subtree ではなく product 側 wrapper task として扱う
