<!--
@dependency-start
contract reference
responsibility Documents the dedicated wiki publication tool.
upstream design ../agent-canon/agent-canon-github-remote.md defines canonical GitHub wiki remote policy.
upstream design ../../agents/skills/wiki-publication.md owns workflow and source/projection boundary.
upstream implementation ../../tools/agent_tools/wiki_publish.py owns deterministic publish gates.
downstream implementation ../../tests/agent_tools/test_wiki_publish.py validates the CLI and blocker transitions.
@dependency-end
-->

# Wiki Publication Tool

`tools/agent_tools/wiki_publish.py` publishes AgentCanon wiki pages to a separate
`owner/repo.wiki.git` sidecar, binds the entire top-level page set to exact source
commit identity, and performs deterministic gates before publication.

## Command

```bash
python3 tools/agent_tools/wiki_publish.py \
  --wiki-root /path/to/agent-canon.wiki \
  --source-root . \
  --source-commit <40-char-sha1> \
  --repo iwashita-nozomu/agent-canon \
  --writer "$USER" \
  --reviewer "$REVIEWER" \
  --summary-out reports/agents/wiki-publication.json
```

To publish, add the reviewed digest:

```bash
python3 tools/agent_tools/wiki_publish.py \
  --wiki-root /path/to/agent-canon.wiki \
  --source-root . \
  --source-commit <40-char-sha1> \
  --repo iwashita-nozomu/agent-canon \
  --writer "$USER" \
  --reviewer "$REVIEWER" \
  --expected-page-set-digest <sha256> \
  --summary-out reports/agents/wiki-publication.json
```

## Gate Contract

- `REMOTE_UNINITIALIZED` blocker:
  - emitted when the wiki remote has no default branch refs;
  - no mutation or push is attempted.
- Default-branch only:
  - wiki remote is `https://github.com/<repo>.wiki.git`;
  - branch comes only from `git ls-remote --symref <repo>.wiki.git HEAD`;
  - publish uses explicit `HEAD:<default branch>`.
- Source validation:
  - `--source-commit` must be full 40-char hex and a real commit in `--source-root`.
- Page gates:
  - inventory all top-level `*.md` pages;
  - require `Home.md`, `_Sidebar.md`, `_Footer.md`;
  - each page must contain exact `AGENT_CANON_WIKI_SOURCE_COMMIT=<sha>` binding.
- Formatting and digest:
  - checks/prepare runs markdown/math/Mermaid formatting before reviewer approval;
  - deterministic SHA-256 is computed on sorted page paths and prepared bytes;
  - publish requires exact `--expected-page-set-digest` match and rejects mismatch.
- Publish readback:
  - verifies exact local/remote head match after `git push`.

## Official GitHub Wiki Behavior Reference

GitHub wiki pages are hosted in `<repo>.wiki.git`, and the effective published
branch is the remote default branch for that repository.
A wiki page set must be initialized and aligned before clone/push and readback
flows proceed.
