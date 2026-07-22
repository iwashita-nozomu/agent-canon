# Wiki Publication
<!--
@dependency-start
contract skill
responsibility Documents Wiki Publication Workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md skill and workflow registry
upstream design ../canonical/CODEX_WORKFLOW.md tool/skill composition contract
upstream design ./README.md runtime and repository separation contract
upstream implementation ../../tools/agent_tools/wiki_publish.py
downstream implementation ../../.agents/skills/wiki-publication/SKILL.md
@dependency-end
-->

## Use When

- user asks for publishing AgentCanon content to GitHub wiki with an explicit
  default-branch-only, source-bound workflow;
- branch-independent, sidecar-published, reader-projection wiki updates are needed
  (never canonical, never a local project `wiki` directory);
- initial page creation is intentionally separated from page updates and the
  workflow requires an explicit `REMOTE_UNINITIALIZED` blocker state before clone;
- PR-style reviewer separation and source-refined validation are required.

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
   - if remote has no branch refs, the workflow state is typed
     `REMOTE_UNINITIALIZED` and no mutation is attempted;
   - once initialized, fetch and clone the remote default branch, then bind content
     to exact source commit.
4. Normalize page content with the shared Markdown + math + Mermaid formatter,
   write one source-reference marker, then push only the exact remote default
   branch.
5. Read back remote head commit and compare exact equality with local push head.
6. Return a typed summary for writer and independent reviewer checks.

## Output Contract

`tools/agent_tools/wiki_publish.py` emits compact JSON including:

- action (`publish`)
- wiki remote URL
- default branch and page path
- source repo branch/commit
- local and remote head commit
- blocker if any

