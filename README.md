# agent-canon snapshot

このディレクトリは、shared agent canon の committed snapshot です。
将来的には外部 repo `agent-canon` の subtree 取り込み先として使いますが、外部 repo を作る前でも `git clone <template>` 直後に shared canon を参照できるよう、template 側へ実体を含めています。

含むもの:
- `CLAUDE.md`
- `.github/AGENTS.md`
- `.github/copilot-instructions.md`
- `agents/`
- `.agents/skills/`
- `.claude/agents/`
- `.claude/skills/`
- `.codex/README.md`
- `.codex/agents/`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/implementation-waterfall-workflow.md`
- `documents/workflow-references.md`
- `documents/worktree-lifecycle.md`
- `scripts/agent_tools/`
- `scripts/setup_worktree.sh`
- `scripts/worktree_start.sh`
- `scripts/tools/check_worktree_scopes.sh`
- `scripts/tools/create_worktree.sh`
- `scripts/tools/mirror_skill_shims.py`

含まないもの:
- product root entrypoint
  - root `AGENTS.md`
  - root `.codex/config.toml`
- implementation / experiment / environment 本体
  - `python/`
  - `experiments/`
  - `docker/`
  - `notes/`

更新:

```bash
bash scripts/sync_agent_canon.sh link-root
```

既存の `snapshot` command は後方互換 alias として残しています。

外部 repo ができたら、次で upstream sync へ移れます。

```bash
bash scripts/sync_agent_canon.sh add git@github.com:<org>/agent-canon.git
bash scripts/sync_agent_canon.sh pull
bash scripts/sync_agent_canon.sh push
```
