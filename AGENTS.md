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
- `documents/README.md`
- `agents/README.md`
- `agents/workflows/README.md`
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
- first-reader 向けの入口は `README.md` -> `documents/README.md` -> `agents/README.md` -> `agents/workflows/README.md` の順にたどれるよう保つ
- 広い概念、長い user request、文書統合、薄い文書洗い出しでは、広域 `rg` の前に `agent-canon semantic-index search --query-file <file> --top-k <N> --format text|jsonl` または `agent-canon semantic-index thin-docs --top-k <N> --format text` を試す
- skill、tool、workflow、HTML report、実験 script を追加または変更するときは、先に既存資産の調査、次に責務境界の解析、その後に実装へ入る。この順序と再利用しなかった候補は run bundle または work log に残す
- prompt、routing、subagent-config の shared canon を直す task では、親が policy prose を直接広く書き換える前に `prompt_config_reviewer` で prompt/config audit を切り、重複 surface と最小差分を先に確定する
- AGENTS / ROOT_AGENTS に禁止事項を増やす前に、warning hook、checker、closeout artifact gate、role TOML、または workflow eval に逃がせるかを決める。hook は原則 fail-open の context / evidence 収集面とし、prompt secret など高確信の公開事故以外を runtime blocker にしない
- root entrypoint wrapper の変更は、この tree ではなく template / 派生 repo 側の wrapper task として扱う
