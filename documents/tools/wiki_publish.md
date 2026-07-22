<!--
@dependency-start
contract reference
responsibility Documents the dedicated wiki publication tool.
upstream design ../agent-canon-github-remote.md defines canonical GitHub wiki remote policy.
upstream design ../../agents/skills/wiki-publication.md owns workflow and source/projection boundary.
upstream implementation ../../tools/agent_tools/wiki_publish.py owns deterministic publish gates.
downstream implementation ../../tests/agent_tools/test_wiki_publish.py validates the CLI and blocker transitions.
@dependency-end
-->

# Wiki Publication Tool

`tools/agent_tools/wiki_publish.py` publishes AgentCanon pages to a separate
`owner/repo.wiki.git` sidecar, binds each publish to exact source commit identity,
and performs explicit source/reference gates before and after push.

## Command

```bash
python3 tools/agent_tools/wiki_publish.py \
  --repo iwashita-nozomu/agent-canon \
  --source-page README.md \
  --source-branch main \
  --page-name Home.md \
  --writer "$USER" \
  --reviewer "$REVIEWER"
```

Optional summary artifact:

```bash
python3 tools/agent_tools/wiki_publish.py ... --summary-out reports/agents/wiki-publication.json
```

## Gate Contract

- `REMOTE_UNINITIALIZED` blocker:
  - emitted when the wiki remote has no default branch refs;
  - no mutation is attempted before initialization.
- Default-branch only:
  - wiki clone and push target the resolved default branch;
  - push command is explicit `HEAD:<default branch>`.
- Source binding:
  - source page is resolved from `--source-page` and `--source-branch`;
  - formatted page includes `AGENT_CANON_WIKI_SOURCE_COMMIT=<sha1>` marker;
  - publish fails if marker does not match the exact source commit.
- Formatting gates:
  - runs `tools/bin/agent-canon docs format` on the staged copy;
  - writer and reviewer identities must be distinct.
- Readback gate:
  - local and remote head SHA must match after push.

## Official GitHub Wiki Behavior Reference

GitHub wiki pages are hosted in `<repo>.wiki.git`, and the default branch for
that repository is the one that receives active page updates for page visibility.
A wiki page must be initialized before subsequent default-branch clone/push and
readback flows can proceed.
