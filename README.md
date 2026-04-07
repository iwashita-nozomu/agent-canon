# agent-canon snapshot

このディレクトリは、shared agent canon の committed snapshot です。
将来的には外部 repo `agent-canon` の subtree 取り込み先として使いますが、外部 repo を作る前でも `git clone <template>` 直後に shared canon を参照できるよう、template 側へ実体を含めています。

含むもの:
- `agents/`
- `.agents/skills/`
- `.claude/agents/`
- `.claude/skills/`
- `.codex/README.md`
- `.codex/agents/`
- agent 関連の `documents/`
- agent 関連の `scripts/`

含まないもの:
- product root entrypoint
  - root `AGENTS.md`
  - root `.codex/config.toml`
  - root `CLAUDE.md`
  - root `.github/copilot-instructions.md`
- implementation / experiment / environment 本体
  - `python/`
  - `experiments/`
  - `docker/`
  - `notes/`

更新:

```bash
bash scripts/sync_agent_canon.sh snapshot
```

外部 repo ができたら、次で upstream sync へ移れます。

```bash
bash scripts/sync_agent_canon.sh add git@github.com:<org>/agent-canon.git
bash scripts/sync_agent_canon.sh pull
bash scripts/sync_agent_canon.sh push
```
