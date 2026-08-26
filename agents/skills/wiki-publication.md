# Wiki Publication
<!--
@dependency-start
contract skill
responsibility Documents Wiki Publication Workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md skill and workflow registry
upstream design ../canonical/CODEX_WORKFLOW.md tool/skill composition contract
upstream design ./README.md runtime and repository separation contract
upstream implementation ../../tools/agent_tools/wiki_publish.py wiki publication gate tool
downstream implementation ../../.codex/personal/skills/wiki-publication/SKILL.md exposes the runtime skill shim
@dependency-end
-->

## Use When

- user asks for publishing AgentCanon content to GitHub wiki with an explicit
  default-branch-only, source-bound workflow;
- branch-independent, sidecar-published, reader-projection wiki updates are needed
  (never canonical, never a local project `wiki` directory);
- publication is approved in two stages: prepare/check then publish with reviewer digest.

## Scope

This skill owns the wiki publication routing, not experiment pipelines or AgentCanon
submodule pinning. It must not infer keyword routing, branch heuristics, or parent
repo responsibilities.

## Procedure

1. Validate request metadata and writer/reviewer identity.
2. Read `agents/skills/catalog.yaml` entry for `wiki-publication` and the runtime
   skill instructions.
3. Resolve target wiki remote from `<repo>.wiki.git` and perform one deterministic
   projection gate:
   - if remote has no default branch refs, workflow state is typed
     `REMOTE_UNINITIALIZED` and no wiki mutation is attempted;
   - once initialized, clone default branch and require checked-out branch equals it.
4. Inventory all top-level `.md` pages in the wiki sidecar; require
   `Home.md`, `_Sidebar.md`, and `_Footer.md`.
5. `tools/bin/agent-canon docs format` each page to normalized bytes,
   bind the exact source commit marker,
   and compute deterministic SHA-256 over sorted page path+bytes.
6. In check mode, return digest and summary; publish requires
   `--expected-page-set-digest` to match exactly that digest.
7. On publish, commit the prepared page set, push only `HEAD:<default branch>`,
   and read back exact remote branch head.

## Output Contract

`tools/agent_tools/wiki_publish.py` emits compact JSON including:

- action (`publish`)
- wiki remote URL
- default branch
- source repo commit
- page-set digest and page count
- local and remote head commit on publish
- typed blockers if any
